import streamlit as st
import pandas as pd
import requests
import io
import pytz
import random
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
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
    # 確保使用目前支援最廣的 flash 模型名稱
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
        
        # 將資料轉換成文字，過濾掉空的欄位
        details = "\n".join([f"{k}：{v}" for k, v in data_dict.items() if v])
        
        # 🌟 優化：加強風格的「專業感」與「條列式」限制
        style_prompts = {
            "在地專業": "【專家分析視角】語氣穩重專業、客觀。著重於大甲區的地段發展潛力、市場行情對比、投資報酬與建築工法。讓買方覺得這是一筆『精準且保值』的決策。",
            "溫馨感性": "【說故事視角】語氣溫暖但「不廢話」。簡單點出空間帶給家人的實用性與學區/生活圈便利性，勾勒成家願景，但仍須保持房仲的專業俐落。",
            "限時急售": "【高 CP 值視角】語氣節奏快、具說服力。強調『單價優勢』、『市場稀有度』與『錯過可惜的絕佳賣點』，用市場數據或性價比來創造急迫感。",
            "精簡快訊": "【直擊痛點視角】極簡風格，完全不廢話。去除所有形容詞，只留下買方最在意的核心賣點，適合講求效率的投資客或快速瀏覽的讀者。"
        }
        
        # 判斷是否有網址，有則加入呼籲文字
        link_text = f"👉 **詳細資訊與更多照片請看：**\n{data_dict.get('專屬網址')}\n" if data_dict.get('專屬網址') else ""

        # 🌟 核心修改：嚴格限制 AI 的輸出結構，強制先給資料、再給條列式亮點
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
        4. 【排版規範】：段落之間必須空行，保持畫面乾淨專業。Emoji 僅作畫龍點睛，勿過度使用導致眼花撩亂。

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
    def add_watermark(image_bytes, text="有巢氏大甲店"):
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        txt = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt)
        w, h = img.size
        try:
            # 系統會在這裡尋找同資料夾下的字體檔
            font = ImageFont.truetype("NotoSansTC-Regular.ttf", int(h / 18))
        except Exception as e:
            # 若找不到字體檔，給予明確警告
            st.error("⚠️ 系統找不到 NotoSansTC-Regular.ttf 字體檔，請確認檔案已放入資料夾！")
            font = ImageFont.load_default()
            
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        margin = int(w * 0.03)
        
        # 加上陰影讓白字在淺色背景也能看清楚
        draw.text((w - tw - margin + 2, h - th - margin + 2), text, font=font, fill=(0, 0, 0, 150))
        draw.text((w - tw - margin, h - th - margin), text, font=font, fill=(255, 255, 255, 200))
        return Image.alpha_composite(img, txt).convert("RGB")

def upload_photo_to_fb(image_obj):
    buf = io.BytesIO()
    image_obj.save(buf, format='JPEG', quality=90)
    buf.seek(0)
    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos"
    res = requests.post(url, data={'published': 'false', 'access_token': FB_TOKEN}, files={'source': buf})
    return res.json().get('id'), res.json().get('error')

def post_to_feed(message, photo_ids, scheduled_time=None):
    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
    payload = {'message': message, 'access_token': FB_TOKEN}
    if scheduled_time:
        payload['published'] = 'false'
        payload['scheduled_publish_time'] = scheduled_time
    for i, p_id in enumerate(photo_ids):
        payload[f'attached_media[{i}]'] = f'{{"media_fbid": "{p_id}"}}'
    return requests.post(url, data=payload)

# 狀態重置函數
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
    with st.form("pro_master_form"):
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
            # 🌟 新增：專屬網址欄位
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
            target_weekday = "一"
            
            if mode == "📅 連續多週排程":
                col_w, col_t = st.columns(2)
                with col_w:
                    target_weekday = st.selectbox("每週固定星期幾？", ["一", "二", "三", "四", "五", "六", "日"])
                with col_t:
                    post_time = st.time_input("發文時間", datetime.strptime("18:00", "%H:%M").time())
                
                schedule_weeks = st.slider("連續排程未來幾週？ (最多8週)", 1, 8, 4)

        gen_btn = st.form_submit_button("🤖 啟動 AI 批量生成")

    if uploaded_files:
        st.markdown("### 🖼️ 浮水印預覽")
        try:
            preview_img = AISmartHelper.add_watermark(uploaded_files[0].getvalue())
            st.image(preview_img, caption="照片壓上浮水印後的實際效果", width=300)
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
                st.session_state['uploaded_files_data'] = [file.getvalue() for file in uploaded_files]
            
            # 🌟 將網址也打包進去給 AI
            data_payload = {
                "物件名稱": name, "總價": f"{price}萬", "建坪": f"{ping}坪", "地坪": f"{land_ping}坪",
                "格局": layout, "車位": parking, "專屬網址": link, "特色": features
            }
            
            st.session_state['generated_posts'] = []
            now = datetime.now(tw_tz)
            
            with st.spinner(f"AI 正在為您生成 {schedule_weeks} 篇不同風格的貼文..."):
                for i in range(schedule_weeks):
                    if mode == "📅 連續多週排程":
                        weekdays_map = {"一":0, "二":1, "三":2, "四":3, "五":4, "六":5, "日":6}
                        days_ahead = weekdays_map[target_weekday] - now.weekday()
                        if days_ahead <= 0 and i == 0: 
                            days_ahead += 7
                        target_date = now + timedelta(days=days_ahead + (i * 7))
                        target_dt = tw_tz.localize(datetime.combine(target_date.date(), post_time))
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
                            img = AISmartHelper.add_watermark(file_bytes)
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
# 4. Tab 2: 粉專成效儀表板 (真實數據版)
# ==========================================
with tab2:
    st.header("📈 粉絲專頁近期成效 (真實數據連線)")
    st.markdown("串接 Facebook 官方 Insights API，讀取粉專真實的觸及與互動狀況。")
    
    if st.button("🔄 撈取最新 FB 數據"):
        if not FB_PAGE_ID or not FB_TOKEN:
            st.error("⚠️ 缺少 FB_PAGE_ID 或 FB_TOKEN，無法連線。")
        else:
            with st.spinner("正在與 Facebook 連線撈取真實數據..."):
                # FB Insights API 網址 (抓取近 7 天的觸及與互動)
                url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/insights"
                params = {
                    'metric': 'page_impressions,page_post_engagements',
                    'period': 'day',
                    'date_preset': 'last_7d',
                    'access_token': FB_TOKEN
                }
                
                try:
                    res = requests.get(url, params=params)
                    fb_data = res.json()
                    
                    if 'error' in fb_data:
                        st.error(f"❌ FB API 發生錯誤：{fb_data['error']['message']}")
                        st.info("💡 提示：請確認您的 Token 是否過期，或是否已在 Meta 開發者後台開啟 `pages_read_engagement` 權限。")
                    else:
                        # 解析 FB 回傳的 JSON 結構
                        insights = fb_data.get('data', [])
                        
                        impressions_dict = {}
                        engagements_dict = {}
                        
                        for metric in insights:
                            metric_name = metric['name']
                            for val in metric['values']:
                                # 擷取日期部分 (例如 2024-05-01)
                                date_str = val['end_time'].split('T')[0]
                                if metric_name == 'page_impressions':
                                    impressions_dict[date_str] = val['value']
                                elif metric_name == 'page_post_engagements':
                                    engagements_dict[date_str] = val['value']
                        
                        # 將字典轉換為 Pandas DataFrame，並處理空值
                        df = pd.DataFrame({
                            "👀 觸及人數 (Impressions)": impressions_dict,
                            "👍 互動次數 (Engagements)": engagements_dict
                        }).fillna(0)
                        
                        if not df.empty:
                            met_col1, met_col2 = st.columns(2)
                            met_col1.metric("近 7 天總觸及", f"{int(df['👀 觸及人數 (Impressions)'].sum()):,}")
                            met_col2.metric("近 7 天總互動", f"{int(df['👍 互動次數 (Engagements)'].sum()):,}")
                            
                            st.markdown("---")
                            st.line_chart(df, use_container_width=True)
                            st.success("✅ 成功載入 Facebook 真實數據！")
                        else:
                            st.warning("⚠️ 撈不到近期的數據，粉專最近可能沒有任何活動。")
                            
                except Exception as e:
                    st.error(f"連線失敗：{e}")
