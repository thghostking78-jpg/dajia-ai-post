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
YOUR_PUBLIC_LOGO_URL = 'https://raw.githubusercontent.com/your-repo/logo.png' # 可替換為你的 Logo 網址

st.set_page_config(page_title="大甲房產發文小幫手", page_icon="🏠", layout="wide")

FB_PAGE_ID = st.secrets.get("FB_PAGE_ID", "")
FB_TOKEN = st.secrets.get("FB_TOKEN", "")
GEMINI_KEY = st.secrets.get("GEMINI_KEY", "")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    # 確保使用目前支援最廣的 flash 模型名稱
    ai_model = genai.GenerativeModel('gemini-1.5-flash')

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
        
        # 🌟 優化：加強風格差異化與視覺吸引力
        style_prompts = {
            "在地專業": "【專家分析視角】語氣穩重專業。強調大甲在地地段發展潛力、市場行情對比、投資報酬率。讓買方覺得這是一筆『聰明且保值』的決策。適度使用 📊、📈、🏠 等符號。",
            "溫馨感性": "【說故事視角】語氣溫暖動人。描繪一家人在此生活的美好畫面，強調『成家夢想』、空間帶給家人的溫度、以及大甲生活圈的人情味與便利。讓買方產生『這就是未來的家』的憧憬。適度使用 ❤️、👨‍👩‍👧‍👦、☕ 等符號。",
            "限時急售": "【FOMO 錯失恐懼視角】語氣急迫、充滿爆發力。強烈營造物件『極度稀有』、『超值破盤價』、『即將秒殺』的氛圍，促使滑到貼文的人立刻想打電話預約。大量使用 🚨、🔥、⏳、⚡ 等強烈視覺符號。",
            "精簡快訊": "【直擊痛點視角】極簡風格，不廢話。直接列出買方最在意的：標題、總價、坪數與『一句最強大且誘人的特色』。適合快速滑 IG/FB 的讀者，總字數嚴格控制在 100 字內。使用 ✅ 條列。"
        }
        
        prompt = f"""
        你是一位台中大甲區的頂尖房仲行銷專家，目前在『有巢氏房屋大甲加盟店』服務。
        請根據以下物件資訊撰寫一份吸睛的 FB 貼文。
        
        【文案風格與語氣設定】: {style_prompts.get(style)}
        
        【物件資訊】:
        {details}
        
        【撰寫要求】:
        1. 標題必須極具吸引力，並包含物件名稱與總價。
        2. 段落之間必須有適當的空行，方便手機閱讀，絕對不能擠成一團。
        3. 巧妙運用 Emoji 表情符號增加視覺亮點，但勿過度眼花撩亂。
        4. 規格部分請清晰排版 (如: 💰總價 / 📐建坪 / 🚪格局)。

        【結尾格式要求】 (請原封不動放在文案最後):
        ---
        🏠 **有巢氏房屋台中大甲店 (孔子廟對面)**
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
        # 注意：需確保有 NotoSansTC-Regular.ttf，否則中文會變方塊
        try:
            font = ImageFont.truetype("NotoSansTC-Regular.ttf", int(h / 18))
        except:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        margin = int(w * 0.03)
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

# 顯示 Logo 圖片
try:
    if YOUR_PUBLIC_LOGO_URL:
        st.image(YOUR_PUBLIC_LOGO_URL, width=150)
except:
    pass # 如果網址失效就略過，避免系統報錯

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
            # 🌟 將 "無" 移到第一位，這樣系統就會預設選擇它了！
            parking = st.selectbox("🚗 車位", ["無", "自有車庫", "坡道平面", "門口停車"])
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

    # 🌟 新增：浮水印首圖預覽 (在表單外即時顯示)
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
            
            data_payload = {
                "物件名稱": name, "總價": f"{price}萬", "建坪": f"{ping}坪", "地坪": f"{land_ping}坪",
                "格局": layout, "車位": parking, "特色": features
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
                        target_dt = now + timedelta(minutes=15) # 立即發佈預留緩衝
                    
                    # 🌟 修復 Bug: FB 規定排程時間必須大於現在時間 10-15 分鐘以上
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
                                st.session_state['post_success'] = True # 標記發佈成功

        # 🌟 新增：發佈成功後的狀態重置按鈕
        with col_reset:
            if st.session_state.get('post_success', False):
                if st.button("✨ 完成並建立下一筆", use_container_width=True):
                    st.session_state['post_success'] = False
                    reset_app_state()

# ==========================================
# 4. Tab 2: 粉專成效儀表板
# ==========================================
with tab2:
    st.header("📈 粉絲專頁近期成效 (近 7 天趨勢)")
    st.markdown("這裡可以讓您快速掌握近期發文的觸及率與互動狀況，幫助您調整文案策略！")
    
    if st.button("🔄 載入最新數據"):
        with st.spinner("正在與 Facebook 連線撈取數據..."):
            # 💡 實務上這裡會呼叫 Graph API，例如：
            # url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/insights?metric=page_impressions,page_engaged_users&period=day&access_token={FB_TOKEN}"
            # res = requests.get(url).json()
            
            # 目前先產生模擬數據供您確認畫面與圖表樣式
            dates = [(datetime.now() - timedelta(days=i)).strftime("%m-%d") for i in range(6, -1, -1)]
            mock_data = pd.DataFrame({
                "日期": dates,
                "👀 觸及人數 (Reach)": [random.randint(800, 3500) for _ in range(7)],
                "👍 互動次數 (Engagement)": [random.randint(50, 400) for _ in range(7)]
            }).set_index("日期")
            
            # 顯示重點指標
            met_col1, met_col2, met_col3 = st.columns(3)
            met_col1.metric("本週總觸及", f"{mock_data['👀 觸及人數 (Reach)'].sum():,}", "12% 相較上週")
            met_col2.metric("本週總互動", f"{mock_data['👍 互動次數 (Engagement)'].sum():,}", "5% 相較上週")
            met_col3.metric("目前排程中貼文", f"{schedule_weeks if 'schedule_weeks' in locals() else 0} 篇")
            
            st.markdown("---")
            # 繪製趨勢圖
            st.line_chart(mock_data, use_container_width=True)
            st.caption("備註：此圖表目前帶入模擬數據，需開啟 FB APP 的 insights 權限後替換為真實 API。")
