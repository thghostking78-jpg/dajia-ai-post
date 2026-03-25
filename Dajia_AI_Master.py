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
# 0. 頁面設定
# ==========================================
st.set_page_config(page_title="有巢氏大甲 AI 控盤 Master", page_icon="🏠", layout="wide")

# ==========================================
# 1. 簡單密碼鎖系統
# ==========================================
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.warning("🔒 這是有巢氏大甲店內部專用系統，請輸入通關密語。")
        pwd = st.text_input("輸入密碼", type="password")
        if pwd == "9988":  # 密碼已更新為 9988
            st.session_state["password_correct"] = True
            st.rerun()
        elif pwd:
            st.error("❌ 密碼錯誤，請詢問管理員。")
        return False
    return True

if not check_password():
    st.stop()

# ==========================================
# 2. 核心安全設定與防呆
# ==========================================
FB_PAGE_ID = st.secrets.get("FB_PAGE_ID", "185076618218504")
FB_TOKEN = st.secrets.get("FB_TOKEN", "")
GEMINI_KEY = st.secrets.get("GEMINI_KEY", "")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    # 使用你指定的最新版 2.5 flash 模型
    ai_model = genai.GenerativeModel('gemini-2.5-flash')

# ==========================================
# 3. 智慧功能類別 
# ==========================================
class AISmartHelper:
    @staticmethod
    def generate_copy(name, location, ping, land_ping, price, layout, floor, age, parking, features):
        if not GEMINI_KEY:
            return "⚠️ 系統錯誤：找不到 Gemini API 金鑰！請確認是否已在 Streamlit 後台設定 Secrets。"
            
        # 動態組合文案條件
        details = f"物件名稱：{name}\n"
        if location: details += f"地點：{location}\n"
        if ping: details += f"建坪：{ping}\n"
        if land_ping: details += f"地坪：{land_ping}\n"
        if price: details += f"總價：{price}\n"
        if layout: details += f"格局：{layout}\n"
        if floor: details += f"樓層：{floor}\n"
        if age: details += f"屋齡：{age}\n"
        if parking: details += f"車位：{parking}\n"
        if features: details += f"特色：{features}\n"
        
        prompt = f"""
        你是一位大甲區房仲行銷專家。請為以下物件撰寫一份吸引人的 Facebook 貼文：
        
        【物件資訊】
        {details}
        
        請包含：
        1. 吸引人的第一句話 (要有溫度)
        2. 清晰的物件基本資料與優點列點 (使用 Emoji，請確保把上述有提供的資訊都寫進去)
        3. 呼籲行動 (歡迎預約賞屋)
        4. 標籤 #大甲房產 #大甲買屋 #有巢氏房屋
        
        只要給我文案內文就好，不用自我介紹。
        """
        try:
            return ai_model.generate_content(prompt).text
        except Exception as e:
            return f"AI 生成失敗，錯誤訊息：{e}"

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
# 4. FB API 溝通模組 (新增精準錯誤回報)
# ==========================================
def upload_to_fb(image_obj):
    buf = io.BytesIO()
    image_obj.save(buf, format='JPEG', quality=95)
    buf.seek(0)
    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos"
    res = requests.post(url, data={'published': 'false', 'access_token': FB_TOKEN}, files={'source': buf})
    res_data = res.json()
    
    # 檢查是否有錯誤
    if 'error' in res_data:
        return None, res_data['error'].get('message', 'FB API 未知錯誤')
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
        location = st.text_input("📍 鄰近地點/商圈", placeholder="選填：近大甲車站")
        price_raw = st.text_input("💰 總價 (打數字即可)", placeholder="例如：1280")
        ping_raw = st.text_input("📐 建坪 (打數字即可)", placeholder="例如：35.8")
        land_ping_raw = st.text_input("🌲 地坪 (打數字即可)", placeholder="例如：25.5")
        
    with col2:
        st.markdown("##### 📏 規格細節")
        layout_raw = st.text_input("🚪 格局 (打3個數字)", placeholder="例如：322")
        floor_raw = st.text_input("🏢 樓層 (選填，打X/Y或數字)", placeholder="例如：5/12 或 4")
        age_raw = st.text_input("📅 屋齡 (選填，打數字即可)", placeholder="例如：15 或 預售")
        parking_raw = st.text_input("🚗 車位 (選填)", placeholder="例如：平面、機械、無")
        features = st.text_area("✨ 物件特色 (選填)", placeholder="採光佳、近學區、免整理...", height=68)
        
    with col3:
        st.markdown("##### 📸 附件與發佈設定")
        link = st.text_input("🔗 官網詳情連結", placeholder="請貼上網址")
        uploaded_files = st.file_uploader("📸 上傳物件照片 (多選)", type=['jpg','png','jpeg'], accept_multiple_files=True)
        
        publish_mode = st.radio("發佈方式", ["⚡ 立即發佈", "🕒 預約排程"], horizontal=True)
        
        if publish_mode == "🕒 預約排程":
            default_time = (datetime.now() + timedelta(minutes=30)).time()
            c_date, c_time = st.columns(2)
            sc_date = c_date.date_input("首發日期")
            sc_time = c_time.time_input("發佈時間", value=default_time)
            repeat_weeks = st.number_input("🔁 往後重複幾週？", min_value=1, max_value=10, value=1)

    gen_btn = st.form_submit_button("🤖 第一步：產生 AI 專業文案")

# --- 處理輸入防呆轉換 ---
display_price = f"{price_raw} 萬" if price_raw.isnumeric() else price_raw
display_ping = f"{ping_raw} 坪" if ping_raw.replace('.', '', 1).isdigit() else ping_raw
display_land_ping = f"{land_ping_raw} 坪" if land_ping_raw.replace('.', '', 1).isdigit() else land_ping_raw
display_age = f"{age_raw} 年" if age_raw.isnumeric() else age_raw
display_parking = parking_raw

display_layout = layout_raw
if len(layout_raw) == 3 and layout_raw.isnumeric():
    display_layout = f"{layout_raw[0]}房 {layout_raw[1]}廳 {layout_raw[2]}衛"

display_floor = floor_raw
if "/" in floor_raw:
    parts = floor_raw.split("/")
    if len(parts) == 2:
        display_floor = f"所在 {parts[0]} 樓 / 總樓層 {parts[1]} 樓"
elif floor_raw.isnumeric():
    display_floor = f"整棟 {floor_raw} 樓"

if gen_btn:
    with st.spinner("AI 靈感湧現中，請稍候 3~5 秒..."):
        st.session_state['master_ai_msg'] = AISmartHelper.generate_copy(
            name, location, display_ping, display_land_ping, display_price, display_layout, display_floor, display_age, display_parking, features
        )

if 'master_ai_msg' in st.session_state:
    st.markdown("---")
    final_msg = st.text_area("📝 第二步：確認與修改文案", value=st.session_state['master_ai_msg'], height=250)
    
    if st.button("🚀 第三步：確認並發佈至 FB", type="primary"):
        if not FB_TOKEN:
            st.error("⚠️ 系統錯誤：找不到 FB_TOKEN！請確認是否已在 Streamlit 後台設定 Secrets。")
            st.stop()
            
        if not uploaded_files:
            st.error("⚠️ 請至少上傳一張照片喔！")
        else:
            tw_tz = pytz.timezone('Asia/Taipei')
            current_unix = int(time.time())
            
            if publish_mode == "🕒 預約排程":
                first_dt = tw_tz.localize(datetime.combine(sc_date, sc_time))
                if int(first_dt.timestamp()) < current_unix + 600:
                    st.error("❌ 依 FB 規定，排程時間必須至少是「現在的 10 分鐘之後」，請微調時間。")
                    st.stop()
            
            with st.spinner("正在處理照片並上傳至 Facebook..."):
                photo_ids = []
                has_upload_error = False
                
                for uploaded_file in uploaded_files:
                    img_processed = AISmartHelper.add_watermark(uploaded_file.read())
                    pid, err_msg = upload_to_fb(img_processed)
                    
                    if pid: 
                        photo_ids.append(pid)
                    else:
                        st.error(f"❌ 照片上傳失敗，FB 系統回報：{err_msg}")
                        has_upload_error = True
                        break # 如果有錯誤就停止上傳其他照片
                
                # 只有在照片全部成功上傳的情況下，才送出貼文
                if photo_ids and not has_upload_error:
                    full_msg = f"{final_msg}\n\n🔗 了解更多詳情：{link}\n#大甲房產 #大甲買屋 #有巢氏房屋"
                    
                    if publish_mode == "⚡ 立即發佈":
                        fb_res = post_feed_action(full_msg, photo_ids, mode="immediate")
                        if fb_res.status_code == 200:
                            st.success(f"✅ 太棒了！「{name}」已成功立即發佈！")
                            st.balloons()
                            del st.session_state['master_ai_msg']
                        else:
                            st.error(f"❌ 貼文發佈失敗，FB 系統回報：{fb_res.json().get('error', {}).get('message', '未知錯誤')}")
                    
                    elif publish_mode == "🕒 預約排程":
                        success_count = 0
                        for w in range(repeat_weeks):
                            future_dt = first_dt + timedelta(days=7*w)
                            unix_time = int(future_dt.timestamp())
                            
                            fb_res = post_feed_action(full_msg, photo_ids, mode="scheduled", unix_timestamp=unix_time)
                            if fb_res.status_code == 200:
                                success_count += 1
                                st.write(f"✅ 已排程：{future_dt.strftime('%Y-%m-%d %H:%M')}")
                            else:
                                err_msg = fb_res.json().get('error', {}).get('message', '未知錯誤')
                                st.error(f"❌ {future_dt.strftime('%Y-%m-%d')} 排程失敗：{err_msg}")
                        
                        if success_count > 0:
                            st.success(f"🎉 成功建立 {success_count} 篇排程貼文！")
                            st.balloons()
                            del st.session_state['master_ai_msg']
