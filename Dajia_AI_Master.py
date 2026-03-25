import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime
from PIL import Image, ImageDraw
import google.generativeai as genai

# ==========================================
# 1. 核心安全設定 (雲端版務必使用 Secrets)
# ==========================================
FB_PAGE_ID = st.secrets.get("FB_PAGE_ID", "185076618218504")
FB_TOKEN = st.secrets.get("FB_TOKEN", "")
GEMINI_KEY = st.secrets.get("GEMINI_KEY", "")

genai.configure(api_key=GEMINI_KEY)
ai_model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="大甲 AI 控盤 Master 雲端版", page_icon="☁️", layout="wide")

# ==========================================
# 2. 智慧功能：浮水印與 FB 上傳
# ==========================================
def add_watermark(image_bytes, text="有巢氏大甲店"):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    txt = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(txt)
    w, h = img.size
    fontsize = int(h / 15)
    draw.text((w - fontsize*6, h - fontsize*1.5), text, fill=(255, 255, 255, 130))
    return Image.alpha_composite(img, txt).convert("RGB")

def upload_to_fb(image_obj):
    buf = io.BytesIO()
    image_obj.save(buf, format='JPEG', quality=95) # 確保高畫質
    buf.seek(0)
    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos"
    res = requests.post(url, data={'published': 'false', 'access_token': FB_TOKEN}, files={'source': buf})
    return res.json().get('id')

# ==========================================
# 3. 主介面
# ==========================================
st.title("☁️ 大甲房產 AI 雲端控盤中心")

tab1, tab2 = st.tabs(["🚀 立即 AI 發佈", "📊 數據中心 (開發中)"])

with tab1:
    with st.form("cloud_form"):
        c1, c2 = st.columns(2)
        name = c1.text_input("🏠 物件名稱", placeholder="大甲車站溫馨兩房")
        price = c1.text_input("💰 總價", placeholder="1,280 萬")
        layout = c1.text_input("📐 格局", placeholder="3房2廳2衛")
        link = c2.text_input("🔗 詳情連結", placeholder="貼上 591 或官網網址")
        
        # 雲端核心：檔案上傳器
        uploaded_files = st.file_uploader("📸 上傳物件照片 (可多選，畫質原圖保留)", type=['jpg','png','jpeg'], accept_multiple_files=True)
        
        features = st.text_area("✨ 物件特色", placeholder="採光好、地段優...")
        gen_btn = st.form_submit_button("🤖 產生 AI 專業文案")

    if gen_btn:
        prompt = f"你是一位大甲房仲專家，請為物件「{name}」寫一份FB文案。價格{price}、格局{layout}、特色{features}。要吸睛、溫馨、多用Emoji。"
        res = ai_model.generate_content(prompt)
        st.session_state['cloud_msg'] = res.text

    if 'cloud_msg' in st.session_state:
        final_msg = st.text_area("📝 文案確認", value=st.session_state['cloud_msg'], height=250)
        
        if st.button("🚀 立即處理照片並發佈到 FB"):
            if not uploaded_files:
                st.error("請先上傳照片喔！")
            else:
                with st.spinner("AI 正在為照片加上防盜浮水印並上傳中..."):
                    photo_ids = []
                    for uploaded_file in uploaded_files:
                        img_processed = add_watermark(uploaded_file.read())
                        pid = upload_to_fb(img_processed)
                        if pid: photo_ids.append(pid)
                    
                    if photo_ids:
                        full_msg = f"{final_msg}\n\n🔗 物件詳情：{link}\n#大甲房產 #有巢氏房屋"
                        fb_url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
                        payload = {'message': full_msg, 'access_token': FB_TOKEN}
                        for i, p_id in enumerate(photo_ids):
                            payload[f'attached_media[{i}]'] = f'{{"media_fbid": "{p_id}"}}'
                        
                        final_res = requests.post(fb_url, data=payload)
                        if final_res.status_code == 200:
                            st.success("✅ 恭喜！物件已成功從雲端發佈到粉絲專頁！")
                            st.balloons()