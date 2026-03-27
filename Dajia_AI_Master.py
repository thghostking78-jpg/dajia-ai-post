import streamlit as st
import pandas as pd
import requests
import io
import pytz
import os
import urllib.request
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
    ai_model = genai.GenerativeModel('gemini-2.5-flash')

tw_tz = pytz.timezone('Asia/Taipei')

# ==========================================
# 1. 安全檢查
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

if not check_password():
    st.stop()

# ==========================================
# 2. 智慧功能類別
# ==========================================
class AISmartHelper:
    @staticmethod
    def generate_copy(data_dict, style="精簡快訊"):
        if not GEMINI_KEY: return "⚠️ 找不到 API Key"
        
        details = "\n".join([f"{k}：{v}" for k, v in data_dict.items() if v])
        
        style_prompts = {
            "在地專業": "【專家分析視角】語氣穩重專業、客觀。著重於大甲區的地段發展潛力、市場行情對比、投資報酬與建築工法。讓買方覺得這是一筆『精準且保值』的決策。",
            "溫馨感性": "【說故事視角】語氣溫暖但「不廢話」。簡單點出空間帶給家人的實用性與學區/生活圈便利性，勾勒成家願景，但仍須保持房仲的專業俐落。",
            "限時急售": "【高 CP 值視角】語氣節奏快、具說服力。強調『單價優勢』、『市場稀有度』與『錯過可惜的絕佳賣點』，用市場數據或性價比來創造急迫感。",
            "精簡快訊": "【直擊痛點視角】極簡風格，完全不廢話。去除所有形容詞，只留下買方最在意的核心賣點，適合講求效率的投資客或快速瀏覽的讀者。"
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
        2. 【物件基本資料】(優先顯示！)：直接將【物件資訊】轉化為清晰的條列式重點（如：💰總價 / 📐建坪 / 🌲地坪 / 🚪格局 / 🚗車位 等），讓客戶第一眼就掌握硬數據。
        3. 【專業分析與優勢】(取代長篇大論)：依據設定的風格，用 3~5 點「條列式」說明物件優勢。請收起過度浮誇的形容詞，改用精準、客觀的房產術語來打動買方。
        4. 【排版規範】：段落之間必須空行，保持畫面乾淨專業。Emoji 僅作畫龍點睛，勿過度使用導致眼花狼狽。

        【結尾格式要求】 (請原封不動放在文案最後):
        ---
        {link_text}🏠 **有巢氏房屋台中大甲店 (孔子廟對面)**
        📞 **賞屋專線：04-26888050**
        📍 **大甲區文武路99號**
        #大甲房產 #大甲買屋 #有巢氏房屋 #台中房地產 #文昌祠
        """
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        try:
            return ai_model.generate_content(prompt, safety_settings=safety_settings).text
        except Exception as e:
            return f"AI 生成失敗：{e}"

    @staticmethod
    def add_watermark(image_bytes, text="有巢氏台中大甲店"):
        # 🌟 0. 雲端下載字體機制 (避開GitHub檔案限制)
        font_filename = "NotoSansCJKtc-Regular.otf"
        if not os.path.exists(font_filename):
            try:
                font_url = "https://raw.githubusercontent.com/googlefonts/noto-cjk/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
                urllib.request.urlretrieve(font_url, font_filename)
            except Exception:
                pass 

        try:
            # 1. 讀取圖片與自動修正手機直拍問題
            img = Image.open(io.BytesIO(image_bytes))
            img = ImageOps.exif_transpose(img)
            
            # 🌟 2. 智慧縮圖 (符合FB最佳畫質且防止記憶體爆滿)
            max_size = (2048, 2048)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # 準備RGBA透明層
            img = img.convert("RGBA")
            txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt_layer)
            w, h = img.size
            
            # 3. 載入字體 (字體大小稍微調大：h/16)
            try:
                font = ImageFont.truetype(font_filename, int(h / 16))
            except Exception:
                st.warning("⚠️ 無法載入中文字體，浮水印可能出現方塊。")
                font = ImageFont.load_default()
            
            # 🌟 4. 優化：清晰且舒服的浮水印 (描邊效果)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
            margin = int(w * 0.03)
            # 水印放置在右下角
            position = (w - tw - margin, h - th - margin)
            
            # 畫上文字描邊 (黑色描邊，stroke_width=2)，這可以讓它在深色背景也明顯
            stroke_color = (0, 0, 0, 255) # 純黑描邊
            main_color = (255, 255, 255, 230) # 白色主文字 (稍微透明，舒服)
            draw.text(position, text, font=font, fill=main_color, stroke_width=2, stroke_fill=stroke_color)
            
            # 複合圖層並回傳RGB
            return Image.alpha_composite(img, txt_layer).convert("RGB")
            
        except Exception as e:
            st.error(f"照片處理失敗，檔案可能損毀：{e}")
            return None

def upload_photo_to_fb(image_obj):
    if not image_obj: return None, "Image processing failed"
    buf = io.BytesIO()
    image_obj.save(buf, format='JPEG', quality=90)
    buf.seek(0)
    # 保持 v25.0
    url = f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}/photos"
    res = requests.post(url, data={'published': 'false', 'access_token': FB_TOKEN}, files={'source': buf})
    return res.json().get('id'), res.json().get('error')

def post_to_feed(message, photo_ids, scheduled_time=None):
    # 保持 v25.0
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
# 3. 主介面 UI
# ==========================================
st.title("🚀 發文小幫手 Master Pro")

if 'generated_posts' not in st.session_state:
    st.session_state['generated_posts'] = []
if 'uploaded_files_data' not in st.session_state:
    st.session_state['uploaded_files_data'] = []

tab1, tab2 = st.tabs(["🚀 AI 自動發文與排程", "📊 粉專成效儀表板"])

with tab1:
    # 🌟 UI部分維持原樣 (已移除st.form，日曆反應即時)
    m_col1, m_col2, m_col3 = st.columns(3)
    
    with m_col1:
        st.subheader("📝 核心資訊")
        name = st.text_input("🏠 物件名稱*", placeholder="例：大甲鎮瀾商圈美墅")
        price = st.number_input("💰 總價 (萬)", min_value=0, step=10, value=1200)
        ping = st.number_input("📐 建坪 (坪)", min_value=0.0, step=0.1, value=45.0)
        land_ping = st.number_input("🌲 地坪 (坪)", min_value=0.0, step=0.1, value=25.0)

    with m_col2:
        st.subheader("📏 規格細節")
        layout = st.text_input("🚪 格局", placeholder="如: 4房2廳3衛")
        parking = st.selectbox("🚗 車位", ["無", "自有車庫", "坡道平面", "門口停車"])
        link = st.text_input("🔗 物件專屬網址 (選填)", placeholder="貼上 591 或官網連結")
        features = st.text_area("✨ 物件特色", placeholder="近學區、採光通風好...", height=70)
        uploaded_files = st.file_uploader("📸 照片 (建議 3-5 張)", type=['jpg','png','jpeg'], accept_multiple_files=True)

    with m_col3:
        st.subheader("📅 多風格排程設定")
        selected_styles = st.multiselect(
            "🎨 選擇要輪替的文案風格", 
            ["在地專業", "溫馨感性", "限時急售", "精簡快訊"], 
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

    st.markdown("---")
    gen_btn = st.button("🤖 啟動 AI 批量生成", type="primary", use_container_width=True)

    if uploaded_files:
        st.markdown("### 🖼️ 浮水印預覽")
        try:
            # 🌟 這裡呼叫水印函數，預設文字已改為「有巢氏台中大甲店」
            preview_img = AISmartHelper.add_watermark(uploaded_files[0].getvalue())
            if preview_img:
                st.image(preview_img, caption="照片壓上浮水印後的實際效果 (描邊更清晰)", width=300)
        except Exception as e:
            st.warning("預覽生成中...")

    # --- 邏輯處理 ---
    if gen_btn:
        if not selected_styles:
            st.error("❌ 請至少選擇一種文案風格！")
        elif not name:
            st.error("❌ 請填寫物件名稱！")
        else:
            if uploaded_files:
                # 🌟 修正照片上傳邏輯 (防止記憶體占用)
                st.session_state['uploaded_files_data'] = [file.getvalue() for file in uploaded_files]
            
            data_payload = {
                "物件名稱": name, "總價": f"{price}萬", "建坪": f"{ping}坪", "地坪": f"{land_ping}坪",
                "格局": layout, "車位": parking, "專屬網址": link, "特色": features
            }
            
            st.session_state['generated_posts'] = []
            now = datetime.now(tw_tz)
            
            with st.spinner(f"AI 正在為您生成 {schedule_weeks} 篇不同風格的貼文..."):
                for i in range(schedule_weeks):
                    if mode == "📅 連續多週排程":
                        target_date = start_date + timedelta(days=i * 7)
                        target_dt = tw_tz.localize(datetime.combine(target_date, post_time))
                    else:
                        target_dt = now + timedelta(minutes=15)
                    
                    min_allowed_time = now + timedelta(minutes=15)
                    if target_dt < min_allowed_time:
                        target_dt = min_allowed_time

                    current_style = selected_styles[i % len(selected_styles)]
                    copy_text = AISmartHelper.generate_copy(data_payload, style=current_style)
                    
                    st.session_state['generated_posts'].append({
                        "發文時間": target_dt,
                        "風格": current_style,
                        "文案": copy_text
                    })

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
                        for idx, file_bytes in enumerate(st.session_state['uploaded_files_data']):
                            # 🌟 這裡使用優化後的水印
                            img = AISmartHelper.add_watermark(file_bytes)
                            pid, err = upload_photo_to_fb(img)
                            if pid: photo_ids.append(pid)
                        
                        if photo_ids:
                            status.write("📝 正在排程貼文...")
                            success_count = 0
                            for post in st.session_state['generated_posts']:
                                t_stamp = int(post['發文時間'].timestamp()) if mode == "📅 連續多週排程" else None
                                # v25.0端點已整合在post_to_feed中
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
# 4. Tab 2: 粉專成效儀表板 (🌟 終極無敵防呆版：直接抓真實互動)
# ==========================================
with tab2:
    st.header("📈 近 7 天貼文成效戰情室 (實際互動數)")
    st.markdown("由於 Facebook 官方鎖蔽了新版粉專的底層曝光數據，我們改為直接抓取最真實的 **「按讚、留言、分享」** 加總數！這能更精準反映客戶對物件的關注度。")
    
    if st.button("🔄 撈取最新真實數據"):
        if not FB_PAGE_ID or not FB_TOKEN:
            st.error("⚠️ 缺少 FB_PAGE_ID 或 FB_TOKEN 設定。")
        else:
            with st.spinner("正在與 Facebook 連線，計算真實互動數據中..."):
                api_base = f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}"
                
                # 計算時間 (7天前)
                now_tw = datetime.now(tw_tz)
                since_time_timestamp = int((now_tw - timedelta(days=7)).timestamp())
                
                # 🌟🌟 終極修正：不碰 Insights！直接抓貼文的讚、留言、分享 🌟🌟
                posts_url = f"{api_base}/published_posts"
                posts_params = {
                    # 直接要求 FB 給我們貼文建立時間，以及讚數、留言數、分享數的總和
                    'fields': 'created_time,likes.summary(true),comments.summary(true),shares',
                    'since': since_time_timestamp,
                    'access_token': FB_TOKEN
                }
                
                try:
                    posts_res = requests.get(posts_url, params=posts_params)
                    posts_data = posts_res.json()
                    
                    if 'error' in posts_data:
                        st.error(f"❌ 無法撈取貼文：{posts_data['error']['message']}")
                    else:
                        posts = posts_data.get('data', [])
                        
                        if not posts:
                            st.warning("⚠️ 粉專近 7 天內尚未發佈任何貼文喔，所以沒有數據可以生成。快用排程功能發一篇吧！")
                        else:
                            # 準備日期範圍列表 (近 7 天)
                            last_7_days_list = [(now_tw - timedelta(days=i)).strftime('%m-%d') for i in range(6, -1, -1)]
                            
                            # 初始化字典
                            post_count_dict = {d: 0 for d in last_7_days_list}
                            engagement_dict = {d: 0 for d in last_7_days_list}
                            
                            # 解析每篇貼文的實體數據
                            for p in posts:
                                try:
                                    c_time = datetime.strptime(p['created_time'], '%Y-%m-%dT%H:%M:%S%z').astimezone(tw_tz)
                                    target_date = c_time.strftime('%m-%d')
                                    
                                    # 如果日期在近 7 天內，進行數據累加
                                    if target_date in last_7_days_list:
                                        post_count_dict[target_date] += 1 # 發文數量 +1
                                        
                                        # 抓取讚數、留言數、分享數 (若沒有該數據則預設為 0)
                                        likes = p.get('likes', {}).get('summary', {}).get('total_count', 0)
                                        comments = p.get('comments', {}).get('summary', {}).get('total_count', 0)
                                        shares = p.get('shares', {}).get('count', 0)
                                        
                                        # 總互動 = 讚 + 留言 + 分享
                                        engagement_dict[target_date] += (likes + comments + shares)
                                except Exception:
                                    continue

                            # 生成圖表 DataFrame
                            df_metrics = pd.DataFrame({
                                "📝 發文數量 (Posts)": pd.Series(post_count_dict),
                                "🔥 真實互動數 (讚+留言+分享)": pd.Series(engagement_dict)
                            }).fillna(0)
                            
                            # 🌟 介面顯示
                            met_col1, met_col2 = st.columns(2)
                            met_col1.metric("近 7 天發佈貼文總數", f"{int(df_metrics['📝 發文數量 (Posts)'].sum())} 篇")
                            met_col2.metric("近 7 天獲取總互動", f"{int(df_metrics['🔥 真實互動數 (讚+留言+分享)'].sum())} 次")
                            
                            st.markdown("---")
                            # 顯示圖表
                            st.line_chart(df_metrics, use_container_width=True)
                            st.success(f"✅ 成功撈取！共計算了 {len(posts)} 篇近期貼文的實際互動狀況。")
                            
                except Exception as e:
                    st.error(f"連線撈取成效失敗：{e}")
