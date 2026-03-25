import streamlit as st
import pandas as pd
import os
import requests
import io
import time
import pytz  # 新增：處理台灣時區
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai

# ==========================================
# 0. 頁面設定 (必須在最上方)
# ==========================================
st.set_page_config(page_title="有巢氏大甲 AI 控盤 Master", page_icon="🏠", layout="wide")

# ==========================================
# 1. 核心安全設定
# ==========================================
FB_PAGE_ID = st.secrets.get("FB_PAGE_ID", "185076618218504")
FB_TOKEN = st.secrets.get("FB_TOKEN", "您的FB_Token")
GEMINI_KEY = st.secrets.get("GEMINI_KEY", "您的Gemini_API金鑰")

genai.configure(api_key=GEMINI_KEY)
ai_model = genai.GenerativeModel('gemini-1.5-flash')

# ==========================================
# 2. 智慧功能類別 (AISmartHelper)
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
            # 確保資料夾內有 NotoSansTC-Regular.ttf
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
# 3. FB API 溝通模組 (支援排程)
# ==========================================
def upload_to_fb(image_obj):
    buf = io.BytesIO()
    image_obj.save(buf, format='JPEG', quality=95)
    buf.seek(0)
    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos"
    # 上傳照片時設定 published=false，讓它變成隱藏狀態等待發佈
    res = requests.post(url, data={'published': 'false', 'access_token': FB_TOKEN}, files={'source': buf})
    return res.json().get('id')

def post_feed_scheduled(message, photo_ids, unix_timestamp):
    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
    payload = {
        'message': message, 
        'access_token': FB_TOKEN,
        'published': 'false', # 關鍵：告訴 FB 這是一篇排程貼文
        'scheduled_publish_time': unix_timestamp # 關鍵：告訴 FB 何時發佈
    }
    for i, p_id in enumerate(photo_ids):
        payload[f'attached_media[{i}]'] = f'{{"media_fbid": "{p_id}"}}'
    
    return requests.post(url, data=payload)

# ==========================================
# 4. 主介面
# ==========================================
st.title("🚀 大甲房產 AI 雲端無人機 (全自動排程版)")
st.info("💡 這個版本會將貼文直接傳送至 Facebook 原廠的排程系統。設定好後，您可以安心關閉網頁或電腦，FB 時間到會自動發文！")

with st.form("master_form"):
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("🏠 物件名稱", placeholder="大甲車站溫馨兩房")
        price = st.text_input("💰 總價", placeholder="1,280 萬")
        layout = st.text_input("📐 格局", placeholder="3房 2廳 2衛")
        
        st.markdown("##### 📅 設定發佈時間 (台灣時間)")
        # 預設時間為現在時間的 30 分鐘後 (因為 FB 規定排程必須是大於 10 分鐘後)
        default_time = (datetime.now() + timedelta(minutes=30)).time()
        sc_date = st.date_input("發佈日期")
        sc_time = st.time_input("發佈時間", value=default_time)

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
    
    if st.button("🚀 第三步：立即處理並上傳至 FB 排程中心", type="primary"):
        if not uploaded_files:
            st.error("⚠️ 請至少上傳一張照片喔！")
        else:
            # --- 處理台灣時間與 UNIX Timestamp ---
            tw_tz = pytz.timezone('Asia/Taipei')
            # 組合使用者選的日期與時間
            local_dt = datetime.combine(sc_date, sc_time)
            # 標記為台灣時區
            local_dt = tw_tz.localize(local_dt)
            # 轉換為 FB 需要的 Unix Timestamp
            unix_time = int(local_dt.timestamp())
            
            # 檢查時間是否符合 FB 規定 (必須在未來 10 分鐘到 75 天之內)
            current_unix = int(time.time())
            if unix_time < current_unix + 600:
                st.error("❌ Facebook 規定：排程時間必須至少是「現在時間的 10 分鐘之後」，請將時間往後調整。")
            else:
                with st.spinner("正在為照片上浮水印，並傳送至 Facebook 排程中心... 這可能需要一兩分鐘，請勿關閉網頁。"):
                    photo_ids = []
                    # 處理並上傳照片
                    for uploaded_file in uploaded_files:
                        img_processed = AISmartHelper.add_watermark(uploaded_file.read())
                        pid = upload_to_fb(img_processed)
                        if pid: 
                            photo_ids.append(pid)
                    
                    if photo_ids:
                        full_msg = f"{final_msg}\n\n🔗 了解更多詳情：{link}\n#大甲房產 #大甲買屋 #有巢氏房屋"
                        
                        # 呼叫排程 API
                        fb_res = post_feed_scheduled(full_msg, photo_ids, unix_time)
                        
                        if fb_res.status_code == 200:
                            post_id = fb_res.json().get("id")
                            st.success(f"✅ 太棒了！任務成功提交給 Facebook！")
                            st.info(f"📅 貼文已鎖定於 **{sc_date.strftime('%Y-%m-%d')} {sc_time.strftime('%H:%M')}** 自動公開發表。您現在可以安心關閉電腦了！")
                            st.markdown(f"*(小提醒：您可以前往 Facebook 粉絲專頁的 **Meta Business Suite -> 規劃工具** 中查看或修改這篇排程貼文)*")
                            st.balloons()
                            del st.session_state['master_ai_msg']
                        else:
                            st.error(f"❌ 建立排程失敗：{fb_res.json()}")
