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
# 1. 智慧快取與多模型備援層
# ==========================================

@st.cache_data(show_spinner="AI 正在思考中...", ttl=3600)
def get_cached_ai_response(prompt, model_name, image_bytes=None):
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
        4. 【動態標籤】：請根據物件特性，自動生成 2~3 個精準的 Hashtag (不要自動帶入文昌祠，除非特色有寫)。
        5. 【排版規範】：段落之間必須空行，保持畫面乾淨專業。Emoji 僅作畫龍點睛，勿過度使用。

        【結尾格式要求】 (請原封不動放在文案最後):
        ---
        {link_text}🏠 **有巢氏房屋台中大甲店 (孔子廟對面)**
        📞 **賞屋專線：04-26888050**
        📍 **大甲區文武路99號**
        #大甲房產 #大甲買屋 #有巢氏房屋 #台中房地產
        """
        
        models_to_try = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-flash-latest",
            "gemini-2.0-flash-lite"
        ]
        
        last_error = ""
        for model_name in models_to_try:
            try:
                return get_cached_ai_response(prompt, model_name, image_bytes)
            except Exception as e:
                last_error = str(e)
                if "429" in last_error or "quota" in last_error.lower() or "404" in last_error:
                    st.toast(f"⚠️ {model_name} 暫時不可用，嘗試切換備援模型...")
                    time.sleep(2)  # 加入安全緩衝時間，避免連續請求被擋
                    continue
                else:
                    break 
        
        return f"❌ 所有模型備援皆失敗，最後錯誤訊息：{last_error}"

    @staticmethod
    def add_watermark(image_bytes, text="有巢氏台中大甲店", position_type="右下角", color_theme="專屬綠 (推薦)"):
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
            else: 
                position = (w - tw - margin, h - th - margin)
            
            if color_theme == "專屬綠 (推薦)":
                main_color = (0, 153, 76, 240)    
                stroke_color = (255, 255, 255, 255) 
            elif color_theme == "亮眼黃":
                main_color = (255, 215, 0, 240)     
                stroke_color = (30, 30, 30, 255)    
            else: 
                main_color = (255, 255, 255, 240)   
                stroke_color = (30, 30, 30, 255)    

            shadow_pos = (position[0] + 3, position[1] + 3)
            draw.text(shadow_pos, text, font=font, fill=(0, 0, 0, 150))
            draw.text(position, text, font=font, fill=main_color, stroke_width=3, stroke_fill=stroke_color)
            
            return Image.alpha_composite(img, txt_layer).convert("RGB")
            
        except Exception as e:
            st.error(f"照片處理失敗，檔案可能損毀：{e}")
            return None

# ==========================================
# 4. FB API 溝通層
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
    st.session_state['ordered_images'] = []
    st.session_state['last_uploaded_names'] = []
    st.rerun()

# ==========================================
# 5. 主介面 UI
# ==========================================
st.title("🚀 發文小幫手 Master Pro")
check_fb_token_health() 

if 'generated_posts' not in st.session_state:
    st.session_state['generated_posts'] = []
if 'ordered_images' not in st.session_state:
    st.session_state['ordered_images'] = []
if 'last_uploaded_names' not in st.session_state:
    st.session_state['last_uploaded_names'] = []
if 'watermark_pos' not in st.session_state:
    st.session_state['watermark_pos'] = "右下角"
if 'watermark_color' not in st.session_state:
    st.session_state['watermark_color'] = "專屬綠 (推薦)"

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
        uploaded_files = st.file_uploader("📸 照片上傳 (支援後續手動排序)", type=['jpg','png','jpeg'], accept_multiple_files=True)

    with m_col3:
        st.subheader("📅 多風格排程設定")
        selected_styles = st.multiselect(
            "🎨 選擇要輪替的文案風格", 
            ["在地專業", "溫馨感性", "限時急售", "精簡快訊", "空拍視野"], 
            default=["精簡快訊"]
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

    # 🖼️ 浮水印預覽區與照片排序機制
    if uploaded_files:
        current_names = [f.name for f in uploaded_files]
        if st.session_state['last_uploaded_names'] != current_names:
            st.session_state['ordered_images'] = [f.getvalue() for f in uploaded_files]
            st.session_state['last_uploaded_names'] = current_names

        st.markdown("---")
        st.subheader("🖼️ 照片排序與浮水印設定")
        
        col_pos, col_color = st.columns(2)
        with col_pos:
            watermark_pos = st.radio("📍 選擇浮水印位置", ["右下角", "左下角", "置中"], horizontal=True, index=["右下角", "左下角", "置中"].index(st.session_state['watermark_pos']))
        with col_color:
            watermark_color = st.radio("🎨 選擇浮水印顏色", ["經典白", "專屬綠 (推薦)", "亮眼黃"], horizontal=True, index=["經典白", "專屬綠 (推薦)", "亮眼黃"].index(st.session_state['watermark_color']))
            
        st.session_state['watermark_pos'] = watermark_pos
        st.session_state['watermark_color'] = watermark_color
        
        if st.session_state['ordered_images']:
            cols = st.columns(len(st.session_state['ordered_images']))
            for idx, img_bytes in enumerate(st.session_state['ordered_images']):
                preview_img = AISmartHelper.add_watermark(img_bytes, position_type=watermark_pos, color_theme=watermark_color)
                with cols[idx]:
                    if preview_img:
                        st.image(preview_img, caption=f"發佈順序 {idx+1}", use_container_width=True)
                    
                    # 排序按鈕
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if idx > 0 and st.button("⬅️", key=f"left_{idx}", use_container_width=True):
                            st.session_state['ordered_images'][idx], st.session_state['ordered_images'][idx-1] = st.session_state['ordered_images'][idx-1], st.session_state['ordered_images'][idx]
                            st.rerun()
                    with btn_col2:
                        if idx < len(st.session_state['ordered_images']) - 1 and st.button("➡️", key=f"right_{idx}", use_container_width=True):
                            st.session_state['ordered_images'][idx], st.session_state['ordered_images'][idx+1] = st.session_state['ordered_images'][idx+1], st.session_state['ordered_images'][idx]
                            st.rerun()

    st.markdown("---")
    gen_btn = st.button("🤖 啟動 AI 批量生成", type="primary", use_container_width=True)

    if gen_btn:
        if not selected_styles:
            st.error("❌ 請至少選擇一種文案風格！")
        elif not name:
            st.error("❌ 請填寫物件名稱！")
        else:
            final_link = link if link.strip() else "https://shop.yungching.com.tw/0426888050"
            
            data_payload = {
                "物件名稱": name, "總價": f"{price}萬", "建坪": f"{ping}坪", "地坪": f"{land_ping}坪",
                "樓層": floor, "格局": layout, "車位": parking, "專屬網址": final_link, "特色": features
            }
            
            st.session_state['generated_posts'] = []
            now = datetime.now(tw_tz)
            
            first_image_bytes = st.session_state['ordered_images'][0] if st.session_state['ordered_images'] else None
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
                if not st.session_state['ordered_images']:
                    st.error("❌ 至少要有一張照片才能發佈喔！")
                else:
                    with st.status("正在將任務傳送至 Facebook 系統...", expanded=True) as status:
                        status.write("🖼️ 正在處理浮水印並上傳照片...")
                        photo_ids = []
                        selected_pos = st.session_state.get('watermark_pos', '右下角')
                        selected_color = st.session_state.get('watermark_color', '專屬綠 (推薦)')
                        
                        for idx, file_bytes in enumerate(st.session_state['ordered_images']):
                            img = AISmartHelper.add_watermark(file_bytes, position_type=selected_pos, color_theme=selected_color)
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
# 6. Tab 2: 粉專成效儀表板 (升級防呆版)
# ==========================================
with tab2:
    st.header("📈 粉絲專頁營運戰情室")
    st.markdown("追蹤您的粉專成長軌跡與近期發文紀錄。")
    
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
                        
                        met_col1, met_col2 = st.columns(2)
                        met_col1.metric("👥 總粉絲專頁讚數", f"{int(fan_count):,}")
                        met_col2.metric("🔔 總追蹤人數", f"{int(followers_count):,}")
                        
                        st.markdown("---")
                        
                        # 2. 獲取近期發文紀錄 (嘗試進階參數)
                        posts_url = f"{api_base}/published_posts"
                        
                        # 先嘗試抓取包含讚數與留言數的參數
                        advanced_params = {
                            'fields': 'created_time,message,permalink_url,likes.summary(true),comments.summary(true)',
                            'limit': 15,
                            'access_token': FB_TOKEN
                        }
                        
                        posts_res = requests.get(posts_url, params=advanced_params)
                        posts_data = posts_res.json()
                        
                        # 檢查是否遭遇 #10 或 #100 錯誤
                        has_engagement_permission = True
                        if 'error' in posts_data:
                            err_code = posts_data['error'].get('code')
                            if err_code in [10, 100]:
                                has_engagement_permission = False
                                st.warning("⚠️ 目前的 FB Token 缺少讀取按讚與留言的權限 (pages_read_engagement)，已自動切換為「基本顯示模式」。若需觀看互動數據，請至 Meta 後台重新產生 Token。")
                                
                                # 自動降級：改用昨天安全的基本參數再次請求
                                basic_params = {
                                    'fields': 'created_time,message,permalink_url',
                                    'limit': 15,
                                    'access_token': FB_TOKEN
                                }
                                posts_res = requests.get(posts_url, params=basic_params)
                                posts_data = posts_res.json()
                            else:
                                st.error(f"❌ 獲取貼文失敗：{posts_data['error']['message']}")
                                posts_data = {'data': []}

                        posts = posts_data.get('data', [])
                        
                        if not posts:
                            st.info("近期尚無貼文紀錄。")
                        else:
                            parsed_posts = []
                            seven_days_ago = datetime.now(tw_tz) - timedelta(days=7)
                            top_post = None
                            max_engagement = -1
                            
                            for p in posts:
                                try:
                                    c_time = datetime.strptime(p['created_time'], '%Y-%m-%dT%H:%M:%S%z').astimezone(tw_tz)
                                    msg = p.get('message', '無文字內容 (可能僅有照片或影片)')
                                    url = p.get('permalink_url', '#')
                                    
                                    # 如果有權限，就抓取數據；沒權限就預設為 0
                                    likes = p.get('likes', {}).get('summary', {}).get('total_count', 0) if has_engagement_permission else 0
                                    comments = p.get('comments', {}).get('summary', {}).get('total_count', 0) if has_engagement_permission else 0
                                    engagement = likes + comments
                                    
                                    parsed_posts.append({
                                        'time': c_time,
                                        'message': msg,
                                        'url': url,
                                        'engagement': engagement,
                                        'likes': likes,
                                        'comments': comments
                                    })
                                    
                                    if has_engagement_permission and c_time > seven_days_ago and engagement > max_engagement and engagement > 0:
                                        max_engagement = engagement
                                        top_post = parsed_posts[-1]
                                        
                                except Exception:
                                    continue

                            # 如果有抓到數據且有冠軍貼文，就顯示特別通知
                            if has_engagement_permission and top_post:
                                st.success(f"🔥 **本週成效冠軍發現！** (互動總數: {top_post['engagement']})")
                                st.info(f"👍 按讚: {top_post['likes']} | 💬 留言: {top_post['comments']}\n\n內文片段：{top_post['message'][:50]}...\n\n[👉 點此查看貼文]({top_post['url']})")
                                st.markdown("---")

                            st.subheader("📝 近期發文軌跡 (最新 15 篇)")
                            for p in parsed_posts:
                                msg_preview = p['message'][:80].replace('\n', ' ') + "..."
                                with st.container():
                                    if has_engagement_permission:
                                        # 進階顯示 (包含數據)
                                        col_time, col_msg, col_eng, col_link = st.columns([2, 4, 1.5, 1])
                                        with col_time: st.markdown(f"**🗓️ {p['time'].strftime('%Y-%m-%d %H:%M')}**")
                                        with col_msg: st.text(msg_preview)
                                        with col_eng: st.markdown(f"👍 {p['likes']} | 💬 {p['comments']}")
                                        with col_link: st.markdown(f"[🔗 看成效]({p['url']})")
                                    else:
                                        # 基本顯示 (安全的樣式)
                                        col_time, col_msg, col_link = st.columns([2, 5, 1])
                                        with col_time: st.markdown(f"**🗓️ {p['time'].strftime('%Y-%m-%d %H:%M')}**")
                                        with col_msg: st.text(msg_preview)
                                        with col_link: st.markdown(f"[🔗 看成效]({p['url']})")
                                    st.divider()
                                    
                except Exception as e:
                    st.error(f"系統發生預期外的錯誤：{e}")
