import streamlit as st
import pandas as pd
import requests
import io
import time
import pytz
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai

# ==========================================
# 0. 頁面設定
# ==========================================
st.set_page_config(page_title="有巢氏大甲 AI 控盤 Master", page_icon="🏠", layout="wide")

# ==========================================
# 1. 密碼鎖 (已更新為 9988)
# ==========================================
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.warning("🔒 這是有巢氏大甲店內部專用系統，請輸入通關密語。")
        pwd = st.text_input("輸入密碼", type="password")
        if pwd == "9988":
            st.session_state["password_correct"] = True
            st.rerun()
        elif pwd:
            st.error("❌ 密碼錯誤！")
        return False
    return True

if not check_password():
    st.stop()

# ==========================================
# 2. 核心安全設定
# ==========================================
FB_PAGE_ID = st.secrets.get("FB_PAGE_ID", "185076618218504")
FB_TOKEN = st.secrets.get("FB_TOKEN", "")
GEMINI_KEY = st.secrets.get("GEMINI_KEY", "")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    ai_model = genai.GenerativeModel('gemini-2.5-flash')

# ==========================================
# 3. 智慧 AI 文案助手
# ==========================================
class AISmartHelper:
    @staticmethod
    def generate_copy(name, location, ping, land_ping, price, layout, floor, age, parking, features):
        if not GEMINI_KEY: return "⚠️ 找不到 API 金鑰"
        
        details = f"物件名稱：{name}\n地點：{location}\n建坪：{ping}\n地坪：{land_ping}\n總價：{price}\n格局：{layout}\n樓層：{floor}\n屋齡：{age}\n車位：{parking}\n特色：{features}"
        
        prompt = f"""
        你是一位大甲區房仲行銷專家。請為以下物件撰寫一份吸引人的 Facebook 貼文：
        {details}
        
        【文案要求】
        1. 吸引人的第一句話 (要有溫度、有力道)
        2. 清晰的物件基本資料與優點列點 (使用 Emoji)
        3. 呼籲行動 (歡迎預約賞屋)，並**嚴格包含以下店訊**：
           ---
           🏠 有巢氏房屋大甲加盟店
           📞 電話：04-26888050
           📍 地址：台中市大甲區文武路99號
        4. 標籤 #大甲房產 #大甲買屋 #有巢氏房屋
        只要給我文案內文就好。
        """
        try:
            return ai_model.generate_content(prompt).text
        except Exception as e:
            return f"AI 生成失敗：{e}"

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
        text_w, text_h = bbox[2]-bbox[0], bbox[3]-bbox[1]
        margin = int(w * 0.02)
        x, y = w - text_w - margin, h - text_h - margin
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
    res_data = res.json()
    if 'error' in res_data: return None, res_data['error'].get('message')
    return res_data.get('id'), None

def post_feed_action(message, photo_ids, mode="immediate", unix_timestamp=None):
    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
    payload = {'message': message, 'access_token': FB_TOKEN}
    if mode == "scheduled":
        payload['published'] = 'false'
        payload['scheduled_publish_time'] = unix_timestamp
    else:
        payload['published'] = 'true'
    for i, p_id in enumerate(photo_ids):
        payload[f'attached_media[{i}]'] = f'{{"media_fbid": "{p_id}"}}'
    return requests.post(url, data=payload)

# ==========================================
# 5. 主介面
# ==========================================
st.title("🚀 大甲房產 AI 雲端無人機")

with st.form("master_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("##### 📝 基本資料")
        name = st.text_input("🏠 物件名稱", placeholder="大甲車站溫馨兩房")
        location = st.text_input("📍 鄰近商圈", placeholder="近大甲車站、體育場旁")
        price_raw = st.text_input("💰 總價 (打數字)")
        ping_raw = st.text_input("📐 建坪 (打數字)")
        land_ping_raw = st.text_input("🌲 地坪 (打數字)")
    with col2:
        st.markdown("##### 📏 規格細節")
        layout_raw = st.text_input("🚪 格局 (如322)")
        floor_raw = st.text_input("🏢 樓層 (如5/12)")
        age_raw = st.text_input("📅 屋齡 (打數字)")
        parking = st.text_input("🚗 車位")
        features = st.text_area("✨ 特色描述", height=68)
    with col3:
        st.markdown("##### 📸 發佈設定")
        link = st.text_input("🔗 詳情連結")
        uploaded_files = st.file_uploader("📸 上傳照片 (多選)", type=['jpg','png','jpeg'], accept_multiple_files=True)
        publish_mode = st.radio("模式", ["⚡ 立即發佈", "🕒 預約排程"], horizontal=True)
        if publish_mode == "🕒 預約排程":
            sc_date = st.date_input("日期")
            sc_time = st.time_input("時間", value=(datetime.now() + timedelta(minutes=30)).time())
            repeat_weeks = st.number_input("🔁 重複週數", min_value=1, max_value=10, value=1)
    gen_btn = st.form_submit_button("🤖 第一步：產生 AI 文案")

# --- 自動轉換邏輯 (補上"約") ---
display_price = f"{price_raw} 萬" if price_raw.isnumeric() else price_raw
display_ping = f"約 {ping_raw} 坪" if ping_raw.replace('.','',1).isdigit() else ping_raw
display_land = f"約 {land_ping_raw} 坪" if land_ping_raw.replace('.','',1).isdigit() else land_ping_raw
display_age = f"約 {age_raw} 年" if age_raw.isnumeric() else age_raw
display_layout = f"{layout_raw[0]}房{layout_raw[1]}廳{layout_raw[2]}衛" if len(layout_raw)==3 and layout_raw.isnumeric() else layout_raw

if gen_btn:
    with st.spinner("AI 撰寫中..."):
        st.session_state['master_ai_msg'] = AISmartHelper.generate_copy(name, location, display_ping, display_land, display_price, display_layout, floor_raw, display_age, parking, features)

if 'master_ai_msg' in st.session_state:
    st.markdown("---")
    final_msg = st.text_area("📝 第二步：文案確認", value=st.session_state['master_ai_msg'], height=250)
    if st.button("🚀 第三步：確認發佈至 FB", type="primary"):
        if not uploaded_files: st.error("⚠️ 請上傳照片")
        else:
            with st.spinner("處理中..."):
                p_ids = []
                for f in uploaded_files:
                    pid, err = upload_to_fb(AISmartHelper.add_watermark(f.read()))
                    if pid: p_ids.append(pid)
                    else: st.error(f"❌ 照片失敗：{err}"); st.stop()
                
                full_msg = f"{final_msg}\n\n🔗 詳情：{link}\n#大甲房產 #大甲買屋 #有巢氏房屋"
                if publish_mode == "⚡ 立即發佈":
                    res = post_feed_action(full_msg, p_ids)
                    if res.status_code == 200: st.success("✅ 發佈成功！"); st.balloons(); del st.session_state['master_ai_msg']
                    else: st.error(f"❌ 失敗：{res.json().get('error',{}).get('message')}")
                else:
                    tz = pytz.timezone('Asia/Taipei')
                    dt = tz.localize(datetime.combine(sc_date, sc_time))
                    for w in range(repeat_weeks):
                        post_feed_action(full_msg, p_ids, "scheduled", int((dt + timedelta(days=7*w)).timestamp()))
                    st.success(f"🎉 成功預約 {repeat_weeks} 篇貼文！"); st.balloons(); del st.session_state['master_ai_msg']
