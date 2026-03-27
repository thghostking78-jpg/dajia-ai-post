import streamlit as st
import pandas as pd
import requests
import io
import pytz
import os
import urllib.request
import time
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont, ImageOps
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ==========================================
# 0. 頁面與核心設定
# ==========================================

st.set_page_config(page_title="大甲房產發文小幫手", page_icon="🏠", layout="wide")

FB_PAGE_ID = st.secrets.get("FB_PAGE_ID", "")
FB_TOKEN = st.secrets.get("FB_TOKEN", "")
GEMINI_KEY = st.secrets.get("GEMINI_KEY", "")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

tw_tz = pytz.timezone('Asia/Taipei')

# ==========================================
# 1. 智慧快取與多模型備援層 (緩解 429/404 問題)
# ==========================================

@st.cache_data(show_spinner="AI 正在思考中...", ttl=3600)
def get_cached_ai_response(prompt, model_name, image_bytes=None):
    """
    帶有快取機制的 AI 生成函數。
    model_name 作為快取 Key 的一部分，確保不同模型的結果分開存放。
    """
    model = genai.GenerativeModel(model_name)
    contents = [prompt]
    if image_bytes:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            contents.append(img)
        except Exception:
            pass

    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
    
    response = model.generate_content(contents, safety_settings=safety_settings)
    return response.text

# ==========================================
# 2. 安全檢查與系統狀態
# ==========================================

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.warning("🔒 有巢氏大甲店內部專用系統")
        pwd = st.text_input("輸入通關密語", type="password")
        if pwd == st.secrets.get("SYSTEM_PWD", "9988"):
            st.session_state["password_correct"] = True
            st.rerun()
        elif pwd:
            st.error("密碼錯誤！")
        return False
    return True

def check_fb_token_health():
    """檢查 FB Token 是否過期或失效 (全線使用 v25.0)"""
    if not FB_PAGE_ID or not FB_TOKEN:
        return
    url = f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}?fields=name&access_token={FB_TOKEN}"
    try:
        res = requests.get(url).json()
        if 'error' in res:
            err_msg = res['error'].get('message', '未知錯誤')
            st.error(f"🚨 **FB 權杖 (Token) 異常或已過期！** 貼文排程將會失敗，請重新產出並更新。\n錯誤訊息: {err_msg}")
    except Exception:
        pass 

if not check_password():
    st.stop()

# 側邊欄控制
with st.sidebar:
    st.title("⚙️ 系統控制")
    if st.button("🧹 清除 AI 快取 (重新生成文案)"):
        st.cache_data.clear()
        st.success("快取已清除，下一次生成將會是全新內容！")
    st.divider()
    st.info(f"當前系統時間：\n{datetime.now(tw_tz).strftime('%Y-%m-%d %H:%M')}")

# ==========================================
# 3. 智慧功能類別 (AI 與 影像處理)
# ==========================================

class AISmartHelper:
    @staticmethod
    def generate_copy(data_dict, style="精簡快訊", image_bytes=None):
        if not GEMINI_KEY: return "⚠️ 找不到 API Key"
        
        details = "\n".join([f"{k}：{v}" for k, v in data_dict.items() if v])
        
        style_prompts = {
            "在地專業": "【專家分析視角】語氣穩重專業、客觀。著重於大甲區的地段發展潛力、市場行情對比、投資報酬與建築工法。讓買方覺得這是一筆『精準且保值』的決策。",
            "溫馨感性": "【說故事視角】語氣溫暖但「不廢話」。簡單點出空間帶給家人的實用性與學區/生活圈便利性，勾勒成家願景，但仍須保持房仲的專業俐落。",
            "限時急售": "【高 CP 值視角】語氣節奏快、具說服力。強調『單價優勢』、『市場稀有度』與『錯過可惜的絕佳賣點』，用市場數據或性價比來創造急迫感。",
            "精簡快訊": "【直擊痛點視角】極簡風格，完全不廢話。去除所有形容詞，只留下買方最在意的核心賣點，適合講求效率的投資客或快速瀏覽的讀者。",
            "空拍視野": "【上帝視角】語氣大氣開闊。專注描述基地面寬、地形方正、聯外道路動線與周邊無遮蔽的無敵視野，特別吸引高總價、重視大地坪或農地投資的客群。"
        }
        
        link_text = f"👉 **詳細資訊與更多照片請看：**\n{data_dict.get('專屬網址')}\n" if data_dict.get('專屬網址') else ""

        prompt = f"""
        你是一位台中大甲區的頂尖房仲行銷專家，目前在『有巢氏房屋大甲加盟店』服務。
        請根據以下物件資訊，撰寫一份具備「高專業度」、且「不拖泥帶水」的 FB 貼文。
        
        【文案風格與語氣設定】: 
        {style_prompts.get(style)}
        
        【物件資訊】:
        {details}
        
        【貼文結構嚴格要求】 (請務必依照此順序排版)：
        1. 【吸睛標題】：一行呈現，必須包含物件名稱與總價，簡潔有力。
        2. 【物件基本資料】(優先顯示！)：直接將【物件資訊】轉化為清晰的條列式重點。
        3. 【專業分析與視覺亮點】(取代長篇大論)：依據設定的風格，用 3~5 點「條列式」說明物件優勢。如果有附上照片，請觀察照片並提取真實視覺亮點自然融入。請收起過度浮誇的形容詞，改用精準、客觀的房產術語來打動買方。
        4. 【動態標籤】：請根據物件特性，自動生成 2~3 個精準的 Hashtag。
        5. 【排版規範】：段落之間必須空行，保持畫面乾淨專業。Emoji 僅作畫龍點睛，勿過度使用。

        【結尾格式要求】 (請原封不動放在文案最後):
        ---
        {link_text}🏠 **有巢氏房屋台中大甲店 (孔子廟對面)**
        📞 **賞屋專線：04-26888050**
        📍 **大甲區文武路99號**
        #大甲房產 #大甲買屋 #有巢氏房屋 #台中房地產 #文昌祠
        """
        
        # --- 🚀 核心三重保險備援邏輯 ---
        # 嘗試清單：2.0 Flash -> 1.5 Flash -> 1.5 Flash Latest
        models_to_try = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-latest"]
        
        last_error = ""
        for model_name in models_to_try:
            try:
                return get_cached_ai_response(prompt, model_name, image_bytes)
            except Exception as e:
                last_error = str(e)
                # 如果是額度問題 (429) 或 模型找不到 (404)，就換下一個試試
                if "429" in last_error or "quota" in last_error.lower() or "404" in last_error:
                    st.toast(f"⚠️ {model_name} 暫時不可用，嘗試切換備援模型...")
                    continue
                else:
                    break # 其他類型的錯誤就不再嘗試
        
        return f"❌ 所有模型備援皆失敗，最後錯誤訊息：{last_error}"

    @staticmethod
    def add_watermark(image_bytes, text="有巢氏台中大甲店", position_type="右下角"):
        font_filename = "NotoSansCJKtc-Regular.otf"
        if not os.path.exists(font_filename):
            try:
                font_url = "https://raw.githubusercontent.com/googlefonts/noto-cjk/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
                urllib.request.urlretrieve(font_url, font_filename)
            except Exception:
                pass 

        try:
            img = Image.open(io.BytesIO(image_bytes))
            img = ImageOps.exif_transpose(img)
            
            max_size = (2048, 2048)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            img = img.convert("RGBA")
            txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt_layer)
            w, h = img.size
            
            try:
                font = ImageFont.truetype(font_filename, int(h / 16))
            except Exception:
                font = ImageFont.load_default()
            
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
            margin = int(w * 0.03)
            
            if position_type == "左下角":
                position = (margin, h - th - margin)
            elif position_type == "置中":
                position = ((w - tw) // 2, (h - th) // 2)
            else: # 預設右下角
                position = (w - tw - margin, h - th - margin)
            
            # 畫陰影
            shadow_pos = (position[0] + 3, position[1] + 3)
            draw.text(shadow_pos, text, font=font, fill=(0, 0, 0, 180))
            
            # 畫主文字與描邊
            stroke_color = (30, 30, 30, 255) 
            main_color = (255, 255, 255, 240) 
            draw.text(position, text, font=font, fill=main_color, stroke_width=2, stroke_fill=stroke_color)
            
            return Image.alpha_composite(img, txt_layer).convert("RGB")
            
        except Exception as e:
            st.error(f"照片處理失敗，檔案可能損毀：{e}")
            return None

# ==========================================
# 4. FB API 溝通層 (全線使用 v25.0)
# ==========================================
def upload_photo_to_fb(image_obj):
    if not image_obj: return None, "Image processing failed"
    buf = io.BytesIO()
    image_obj.save(buf, format='JPEG', quality=90)
    buf.seek(0)
    url = f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}/photos"
    res = requests.post(url, data={'published': 'false', 'access_token': FB_TOKEN}, files={'source': buf})
    return res.json().get('id'), res.json().get('error')

def post_to_feed(message, photo_ids, scheduled_time=None):
    url = f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}/feed"
    payload = {'message': message, 'access_token': FB_TOKEN}
    if scheduled_time:
        payload['published'] = 'false'
        payload['scheduled_publish_time'] = scheduled_time
    for i, p_id in enumerate(photo_ids):
        payload[f'attached_media[{i}]'] = f'{{"media_fbid": "{p_id}"}}'
    return requests.post(url, data=payload)

def reset_app_state():
    st.session_state['generated_posts'] = []
    st.session_state['uploaded_files_data'] = []
    st.rerun()

# ==========================================
# 5. 主介面 UI
# ==========================================
st.title("🚀 發文小幫手 Master Pro")
check_fb_token_health() # 檢查 Token 健康度

if 'generated_posts' not in st.session_state:
    st.session_state['generated_posts'] = []
if 'uploaded_files_data' not in st.session_state:
    st.session_state['uploaded_files_data'] = []
if 'watermark_pos' not in st.session_state:
    st.session_state['watermark_pos'] = "右下角"

tab1, tab2 = st.tabs(["🚀 AI 自動發文與排程", "📊 粉專成效儀表板"])

with tab1:
    m_col1, m_col2, m_col3 = st.columns(3)
    
    with m_col1:
        st.subheader("📝 核心資訊")
        name = st.text_input("🏠 物件名稱*", placeholder="例：大甲鎮瀾商圈美墅")
        price = st.number_input("💰 總價 (萬)", min_value=0, step=10, value=1200)
        ping = st.number_input("📐 建坪 (坪)", min_value=0.0, step=0.1, value=45.0)
        land_ping = st.number_input("🌲 地坪 (坪)", min_value=0.0, step=0.1, value=25.0)

    with m_col2:
        st.subheader("📏 規格細節")
        floor = st.text_input("🏢 樓層", placeholder="例：3樓 / 總樓層10樓 (透天填整棟)")
        layout = st.text_input("🚪 格局", placeholder="如: 4房2廳3衛")
        parking = st.selectbox("🚗 車位", ["無", "自有車庫", "坡道平面", "門口停車"])
        link = st.text_input("🔗 物件專屬網址 (選填)", placeholder="若不填，預設帶入大甲店官網首頁")
        features = st.text_area("✨ 物件特色", placeholder="近學區、採光通風好...", height=70)
        uploaded_files = st.file_uploader("📸 照片 (建議 3-5 張)", type=['jpg','png','jpeg'], accept_multiple_files=True)

    with m_col3:
        st.subheader("📅 多風格排程設定")
        selected_styles = st.multiselect(
            "🎨 選擇要輪替的文案風格", 
            ["在地專業", "溫馨感性", "限時急售", "精簡快訊", "空拍視野"], 
            default=["限時急售", "溫馨感性"]
        )
        
        mode = st.radio("發佈模式", ["⚡ 立即發佈", "📅 連續多週排程"], horizontal=True)
        
        schedule_weeks = 1
        post_time = datetime.now(tw_tz).time()
        start_date = datetime.now(tw_tz).date()
        
        if mode == "📅 連續多週排程":
            time_options = []
            for h in range(7, 22):
                time_options.append(f"{h:02d}:00")
                if h != 21: 
                    time_options.append(f"{h:02d}:30")
            
            col_w, col_t = st.columns(2)
            with col_w:
                start_date = st.date_input("🗓️ 首篇發文日期", datetime.now(tw_tz).date())
            with col_t:
                default_idx = time_options.index("18:00") if "18:00" in time_options else 0
                selected_time_str = st.selectbox("⏰ 發文時間", time_options, index=default_idx)
            
            post_time = datetime.strptime(selected_time_str, "%H:%M").time()
            schedule_weeks = st.slider("連續排程未來幾週？ (最多8週)", 1, 8, 4)

    # 🖼️ 浮水印預覽區 (多圖並排)
    if uploaded_files:
        st.markdown("---")
        st.subheader("🖼️ 浮水印預覽與設定")
        watermark_pos = st.radio("📍 選擇浮水印位置", ["右下角", "左下角", "置中"], horizontal=True)
        st.session_state['watermark_pos'] = watermark_pos
        
        try:
            cols = st.columns(len(uploaded_files))
            for idx, file in enumerate(uploaded_files):
                preview_img = AISmartHelper.add_watermark(file.getvalue(), position_type=watermark_pos)
                if preview_img:
                    with cols[idx]:
                        st.image(preview_img, caption=f"預覽圖 {idx+1}", use_container_width=True)
        except Exception as e:
            st.warning("預覽生成中...")

    st.markdown("---")
    gen_btn = st.button("🤖 啟動 AI 批量生成", type="primary", use_container_width=True)

    # --- 邏輯處理 ---
    if gen_btn:
        if not selected_styles:
            st.error("❌ 請至少選擇一種文案風格！")
        elif not name:
            st.error("❌ 請填寫物件名稱！")
        else:
            if uploaded_files:
                st.session_state['uploaded_files_data'] = [file.getvalue() for file in uploaded_files]
            
            final_link = link if link.strip() else "https://shop.yungching.com.tw/0426888050"
            
            data_payload = {
                "物件名稱": name, "總價": f"{price}萬", "建坪": f"{ping}坪", "地坪": f"{land_ping}坪",
                "樓層": floor, "格局": layout, "車位": parking, "專屬網址": final_link, "特色": features
            }
            
            st.session_state['generated_posts'] = []
            now = datetime.now(tw_tz)
            
            first_image_bytes = st.session_state['uploaded_files_data'][0] if st.session_state['uploaded_files_data'] else None
            progress_text = st.empty()
            
            for i in range(schedule_weeks):
                if mode == "📅 連續多週排程":
                    target_date = start_date + timedelta(days=i * 7)
                    target_dt = tw_tz.localize(datetime.combine(target_date, post_time))
                else:
                    target_dt = now + timedelta(minutes=15 + i*1)
                
                min_allowed_time = now + timedelta(minutes=15)
                if target_dt < min_allowed_time:
                    target_dt = min_allowed_time

                current_style = selected_styles[i % len(selected_styles)]
                progress_text.info(f"⏳ 正在生成第 {i+1}/{schedule_weeks} 篇貼文 (風格：{current_style})...")
                
                copy_text = AISmartHelper.generate_copy(data_dict=data_payload, style=current_style, image_bytes=first_image_bytes)
                
                st.session_state['generated_posts'].append({
                    "發文時間": target_dt,
                    "風格": current_style,
                    "文案": copy_text
                })
            
            progress_text.success("✅ AI 批量生成完畢！請在下方預覽確認。")

    # --- 預覽與確認發佈 ---
    if st.session_state['generated_posts']:
        st.markdown("---")
        st.subheader("👀 貼文預覽與修改")
        
        for idx, post in enumerate(st.session_state['generated_posts']):
            with st.expander(f"第 {idx+1} 篇 ➔ 預計發佈：{post['發文時間'].strftime('%Y-%m-%d %H:%M')} (風格：{post['風格']})", expanded=(idx==0)):
                st.session_state['generated_posts'][idx]['文案'] = st.text_area(
                    "修改文案", value=post['文案'], height=250, key=f"text_{idx}"
                )

        col_submit, col_reset = st.columns([3, 1])
        with col_submit:
            if st.button("🚀 確認無誤，全部排程至 Facebook", type="primary", use_container_width=True):
                if not st.session_state['uploaded_files_data']:
                    st.error("❌ 至少要有一張照片才能發佈喔！")
                else:
                    with st.status("正在將任務傳送至 Facebook 系統...", expanded=True) as status:
                        status.write("🖼️ 正在處理浮水印並上傳照片...")
                        photo_ids = []
                        selected_pos = st.session_state.get('watermark_pos', '右下角')
                        
                        for idx, file_bytes in enumerate(st.session_state['uploaded_files_data']):
                            img = AISmartHelper.add_watermark(file_bytes, position_type=selected_pos)
                            pid, err = upload_photo_to_fb(img)
                            if pid: photo_ids.append(pid)
                        
                        if photo_ids:
                            status.write("📝 正在排程貼文...")
                            success_count = 0
                            for post in st.session_state['generated_posts']:
                                t_stamp = int(post['發文時間'].timestamp()) if mode == "📅 連續多週排程" else None
                                fb_res = post_to_feed(post['文案'], photo_ids, scheduled_time=t_stamp)
                                
                                if fb_res.status_code == 200:
                                    success_count += 1
                                else:
                                    st.error(f"❌ 某篇貼文排程失敗：{fb_res.json()}")
                            
                            if success_count == len(st.session_state['generated_posts']):
                                status.update(label="✅ 所有貼文排程成功！", state="complete")
                                st.success(f"🎉 成功排程了 {success_count} 篇貼文！您可以到 Facebook 粉專後台查看。")
                                st.balloons()
                                st.session_state['post_success'] = True

        with col_reset:
            if st.session_state.get('post_success', False):
                if st.button("✨ 完成並建立下一筆", use_container_width=True):
                    st.session_state['post_success'] = False
                    reset_app_state()

# ==========================================
# 6. Tab 2: 粉專成效儀表板
# ==========================================
with tab2:
    st.header("📈 粉絲專頁營運戰情室")
    st.markdown("追蹤您的粉專成長軌跡與近期發文紀錄。(註：因 Meta API 進階審查限制，互動數據需至 FB 後台查看)")
    
    if st.button("🔄 撈取最新營運數據"):
        if not FB_PAGE_ID or not FB_TOKEN:
            st.error("⚠️ 缺少 FB_PAGE_ID 或 FB_TOKEN 設定。")
        else:
            with st.spinner("正在與 Facebook 連線，解析近期營運數據中..."):
                api_base = f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}"
                
                try:
                    # 1. 獲取粉專總粉絲數與追蹤數
                    page_params = {'fields': 'fan_count,followers_count,name', 'access_token': FB_TOKEN}
                    page_data = requests.get(api_base, params=page_params).json()
                    
                    if 'error' in page_data:
                        st.error(f"❌ 無法撈取粉專資料：{page_data['error']['message']}")
                    else:
                        page_name = page_data.get('name', '有巢氏台中大甲店')
                        fan_count = page_data.get('fan_count', 0)
                        followers_count = page_data.get('followers_count', 0)
                        
                        st.success(f"✅ 成功連線至粉專：**{page_name}**")
                        
                        # 2. 獲取近期發文紀錄
                        posts_url = f"{api_base}/published_posts"
                        posts_params = {
                            'fields': 'created_time,message,permalink_url',
                            'limit': 15,
                            'access_token': FB_TOKEN
                        }
                        posts_res = requests.get(posts_url, params=posts_params)
                        posts_data = posts_res.json()
                        
                        # 3. 數據解析與呈現
                        met_col1, met_col2 = st.columns(2)
                        met_col1.metric("👥 總粉絲專頁讚數", f"{int(fan_count):,}")
                        met_col2.metric("🔔 總追蹤人數", f"{int(followers_count):,}")
                        
                        st.markdown("---")
                        st.subheader("📝 近期發文軌跡 (最新 15 篇)")
                        
                        posts = posts_data.get('data', [])
                        if not posts:
                            st.info("近期尚無貼文紀錄。")
                        else:
                            for idx, p in enumerate(posts):
                                try:
                                    c_time = datetime.strptime(p['created_time'], '%Y-%m-%dT%H:%M:%S%z').astimezone(tw_tz)
                                    msg_preview = p.get('message', '無文字內容 (可能僅有照片或影片)')[:80].replace('\n', ' ') + "..."
                                    post_link = p.get('permalink_url', '#')
                                    
                                    with st.container():
                                        col_time, col_msg, col_link = st.columns([2, 5, 1])
                                        with col_time:
                                            st.markdown(f"**🗓️ {c_time.strftime('%Y-%m-%d %H:%M')}**")
                                        with col_msg:
                                            st.text(msg_preview)
                                        with col_link:
                                            st.markdown(f"[🔗 看成效]({post_link})")
                                        st.divider()
                                except Exception:
                                    continue
                                    
                except Exception as e:
                    st.error(f"連線失敗：{e}")
