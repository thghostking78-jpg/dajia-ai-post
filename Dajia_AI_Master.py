import streamlit as st
import pandas as pd
import os
import requests
import io
import time
import pytz
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai

# ==========================================
# 0. 頁面設定 (必須在最上方)
# ==========================================
st.set_page_config(page_title="有巢氏大甲 AI 控盤 Master", page_icon="🏠", layout="wide")

# ==========================================
# 1. 簡單密碼鎖系統 (保護你的粉專)
# ==========================================
def check_password():
    """驗證密碼是否正確"""
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.warning("🔒 這是有巢氏大甲店內部專用系統，請輸入通關密語。")
        pwd = st.text_input("輸入密碼", type="password")
        # 這裡設定你們的團隊密碼，你可以自己改掉 "dajia888"
        if pwd == "9988":
            st.session_state["password_correct"] = True
            st.rerun()
        elif pwd:
            st.error("❌ 密碼錯誤，請詢問管理員。")
        return False
    return True

# 如果密碼沒過，就停止執行後面的所有程式碼
if not check_password():
    st.stop()

# ==========================================
# 2. 核心安全設定
# ==========================================
FB_PAGE_ID = st.secrets.get("FB_PAGE_ID", "185076618218504")
FB_TOKEN = st.secrets.get("FB_TOKEN", "您的FB_Token")
GEMINI_KEY = st.secrets.get("GEMINI_KEY", "您的Gemini_API金鑰")

genai.configure(api_key=GEMINI_KEY)
ai_model = genai.GenerativeModel('gemini-1.5-flash')

# ==========================================
# 3. 智慧功能類別 (AISmartHelper)
# ==========================================
class AISmartHelper:
    @staticmethod
    def generate_copy(name, price, layout, features):
        prompt = f"""
        你是一位大甲區房仲行銷專家。請為以下物件撰寫一份吸引人的 Facebook 貼文：
        物件名稱：{name} | 總價：{price} | 格局：{layout}
        特色：{features}
        請包含：1. 吸引人的第一句話 2. 清晰的物件優點列點 (使用 Emoji) 3. 呼籲行動 4. 標籤 #大甲房產 #有巢氏房屋
        只要給我文案內文就好。
        """
        try:
            return ai_model.generate_content(prompt).text
        except:
            return "AI 生成失敗，請手動輸入文案。"

    @staticmethod
    def add_watermark(image_bytes, text="有巢氏大甲店"):
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        txt = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt)
        w, h = img.size
        try:
            font = ImageFont.truetype("NotoSansTC-Regular.ttf", int(h / 15))
        except:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        margin = int(w * 0.02)
        x = w - text_w - margin
        y = h - text_h - margin
        
        draw.text((x+2, y+2), text, font=font, fill=(0, 0, 0, 150))
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 180))
        
        return Image.alpha_composite(img, txt).convert("RGB")

# ==========================================
# 4. FB API 溝通模組
# ==========================================
def upload_to_fb(image_obj):
    buf = io.BytesIO()
    image_obj.save(buf, format='JPEG', quality=95)
    buf.seek(0)
    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos"
    res = requests.post(url, data={'published': 'false', 'access_token': FB_TOKEN}, files={'source': buf})
    return res.json().get('id')

def post_feed_scheduled(message, photo_ids, unix_timestamp):
    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
    payload = {
        'message': message, 
        'access_token': FB_TOKEN,
        'published': 'false',
        'scheduled_publish_time': unix_timestamp
    }
    for i, p_id in enumerate(photo_ids):
        payload[f'attached_media[{i}]'] = f'{{"media_fbid": "{p_id}"}}'
    return requests.post(url, data=payload)

# ==========================================
# 5. 主介面
# ==========================================
st.title("🚀 大甲房產 AI 雲端無人機 (團隊密碼版)")
st.info("💡 設定好時間與週數後，系統會自動幫您將未來幾週的貼文一次送進 FB 排程中心！")

with st.form("master_form"):
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("🏠 物件名稱", placeholder="大甲車站溫馨兩房")
        price = st.text_input("💰 總價", placeholder="1,280 萬")
        layout = st.text_input("📐 格局", placeholder="3房 2廳 2衛")
        
        st.markdown("##### 📅 設定發佈時間 (台灣時間)")
        default_time = (datetime.now() + timedelta(minutes=30)).time()
        sc_date = st.date_input("首次發佈日期")
        sc_time = st.time_input("發佈時間", value=default_time)
        
        # 新增：重複發佈的週數選擇 (最高限制 10 週，因為 FB 只能排 75 天)
        repeat_weeks = st.number_input("🔁 往後重複發佈幾週？ (1代表只發這一次)", min_value=1, max_value=10, value=1)

    with col2:
        link = st.text_input("🔗 官網詳情連結", placeholder="請貼上網址")
        features = st.text_area("✨ 物件特色", placeholder="採光佳、近學區...")
        uploaded_files = st.file_uploader("📸 上傳物件照片 (多選)", type=['jpg','png','jpeg'], accept_multiple_files=True)

    gen_btn = st.form_submit_button("🤖 第一步：產生 AI 專業文案")

if gen_btn:
    with st.spinner("AI 撰寫中..."):
        st.session_state['master_ai_msg'] = AISmartHelper.generate_copy(name, price, layout, features)

if 'master_ai_msg' in st.session_state:
    final_msg = st.text_area("📝 第二步：確認與修改文案", value=st.session_state['master_ai_msg'], height=200)
    
    if st.button("🚀 第三步：處理並上傳至 FB 排程中心", type="primary"):
        if not uploaded_files:
            st.error("⚠️ 請至少上傳一張照片喔！")
        else:
            tw_tz = pytz.timezone('Asia/Taipei')
            current_unix = int(time.time())
            
            # 先檢查「第一次發文」的時間有沒有太近 (低於10分鐘)
            first_dt = tw_tz.localize(datetime.combine(sc_date, sc_time))
            if int(first_dt.timestamp()) < current_unix + 600:
                st.error("❌ Facebook 規定：排程時間必須至少是「現在時間的 10 分鐘之後」，請將時間往後調整。")
            else:
                with st.spinner("正在處理照片並建立多週排程，這可能需要幾分鐘，請耐心等候..."):
                    # 1. 先處理照片上傳 (一次就好，後面的貼文可以重複用這組照片ID)
                    photo_ids = []
                    for uploaded_file in uploaded_files:
                        img_processed = AISmartHelper.add_watermark(uploaded_file.read())
                        pid = upload_to_fb(img_processed)
                        if pid: 
                            photo_ids.append(pid)
                    
                    if photo_ids:
                        full_msg = f"{final_msg}\n\n🔗 了解更多詳情：{link}\n#大甲房產 #大甲買屋 #有巢氏房屋"
                        success_count = 0
                        
                        # 2. 跑迴圈，依照選定的週數，每週建立一篇排程貼文
                        for w in range(repeat_weeks):
                            # 每次往後加 7 天 (w=0 是第一週, w=1 是第二週...)
                            future_dt = first_dt + timedelta(days=7*w)
                            unix_time = int(future_dt.timestamp())
                            
                            fb_res = post_feed_scheduled(full_msg, photo_ids, unix_time)
                            if fb_res.status_code == 200:
                                success_count += 1
                                st.write(f"✅ 已排程：{future_dt.strftime('%Y-%m-%d %H:%M')}")
                            else:
                                st.error(f"❌ {future_dt.strftime('%Y-%m-%d')} 排程失敗：{fb_res.json()}")
                        
                        if success_count > 0:
                            st.success(f"🎉 太棒了！成功建立 {success_count} 篇排程貼文！您可以關閉網頁了。")
                            st.balloons()
                            del st.session_state['master_ai_msg']
