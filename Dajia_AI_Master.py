import streamlit as st
import pandas as pd
import requests
import io
import pytz
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ==========================================
# 0. 頁面與核心設定
# ==========================================
st.set_page_config(page_title="有巢氏大甲 AI 控盤 Master Pro", page_icon="🏠", layout="wide")

FB_PAGE_ID = st.secrets.get("FB_PAGE_ID", "185076618218504")
FB_TOKEN = st.secrets.get("FB_TOKEN", "")
GEMINI_KEY = st.secrets.get("GEMINI_KEY", "")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    # 🚀 升級點：切換至最新一代更聰明、更快速的 gemini-2.5-flash 模型
    ai_model = genai.GenerativeModel('gemini-2.5-flash')

# 設定台灣時區基準
tw_tz = pytz.timezone('Asia/Taipei')

# ==========================================
# 1. 安全檢查 (還原密碼 9988 設定)
# ==========================================
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.warning("🔒 有巢氏大甲店內部專用系統")
        pwd = st.text_input("輸入通關密語", type="password")
        
        # 🔑 依要求改回：若沒有設定環境變數，預設通關密語為 9988
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
    def generate_copy(data_dict, style="在地專業"):
        if not GEMINI_KEY: return "⚠️ 找不到 API Key"
        
        details = "\n".join([f"{k}：{v}" for k, v in data_dict.items() if v])
        
        style_prompts = {
            "在地專業": "強調大甲在地地段潛力、投資報酬率與專業行情分析。",
            "溫馨感性": "強調成家夢想、空間給予家人的溫度、大甲生活圈的便利與人情味。",
            "限時急售": "營造物件稀有性、超值價格、手刀預約的急迫感。"
        }
        
        prompt = f"""
        你是一位台中大甲區的房仲行銷專家，目前在『有巢氏房屋大甲加盟店』服務。
        請根據以下物件資訊撰寫一份 FB 貼文。
        
        【文案風格】: {style_prompts.get(style)}
        【物件資訊】:
        {details}
        
        【格式要求】:
        1. 標題要吸睛 (包含重點特色)。
        2. 使用適當的 Emoji 增加閱讀舒適度。
        3. 內容需包含物件規格，並轉化為買方看得懂的優點。
        4. 結尾固定附上：
           🏠 **有巢氏房屋大甲加盟店**
           📞 **服務專線：04-26888050**
           📍 **店址：台中市大甲區文武路99號**
        5. 標籤：#大甲房產 #大甲買屋 #有巢氏房屋 #台中房地產
        
        請直接給出文案內容，不要有任何前言或碎念。
        """
        try:
            # 放寬 AI 審查機制，避免正常的房地產廣告詞被攔截
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
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
            font = ImageFont.truetype("NotoSansTC-Regular.ttf", int(h / 18))
        except:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        
        margin = int(w * 0.03)
        draw.text((w - tw - margin + 2, h - th - margin + 2), text, font=font, fill=(0, 0, 0, 150))
        draw.text((w - tw - margin, h - th - margin), text, font=font, fill=(255, 255, 255, 200))
        
        return Image.alpha_composite(img, txt).convert("RGB")

# ==========================================
# 3. FB API 溝通模組
# ==========================================
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

# ==========================================
# ==========================================
# 4. 主介面 UI 與狀態管理
# ==========================================
st.title("🚀 大甲房產 AI 雲端無人機 Pro")
st.caption("自動化文案、浮水印、多平台排程管理系統")

# 初始化 Session State 暫存區
if 'uploaded_files_data' not in st.session_state:
    st.session_state['uploaded_files_data'] = []
if 'current_copy' not in st.session_state:
    st.session_state['current_copy'] = ""

# ✨ 這裡加入雙分頁設定
tab1, tab2 = st.tabs(["🚀 AI 自動發文中心", "📊 粉專成效儀表板"])

# ------------------------------------------
# 分頁 1：原本的發文系統
# ------------------------------------------
with tab1:
    with st.form("pro_master_form"):
        m_col1, m_col2, m_col3 = st.columns(3)
        
        with m_col1:
            st.subheader("📝 核心資訊")
            name = st.text_input("🏠 物件名稱*", placeholder="例：大甲鎮瀾商圈美墅")
            price = st.number_input("💰 總價 (萬)", min_value=0, step=10, value=1200)
            ping = st.number_input("📐 建坪 (坪)", min_value=0.0, step=0.1, value=45.0)
            land_ping = st.number_input("🌲 地坪 (坪)", min_value=0.0, step=0.1, value=25.0)
            unit_price = round(price / ping, 1) if ping > 0 else 0
            st.info(f"💡 自動計算單價：{unit_price} 萬/坪")

        with m_col2:
            st.subheader("📏 規格細節")
            layout = st.text_input("🚪 格局", placeholder="如: 4房2廳3衛")
            floor = st.text_input("🏢 樓層", placeholder="如: 1-4樓 或 5/12")
            age = st.text_input("📅 屋齡", placeholder="如: 5年")
            parking = st.selectbox("🚗 車位", ["自有車庫", "坡道平面", "坡道機械", "門口停車", "無"])
            features = st.text_area("✨ 物件特色", placeholder="近學區、採光通風好...", height=70)

        with m_col3:
            st.subheader("📣 行銷設定")
            copy_style = st.selectbox("🎨 文案語氣", ["在地專業", "溫馨感性", "限時急售"])
            link = st.text_input("🔗 詳情連結", placeholder="官網物件網址")
            uploaded_files = st.file_uploader("📸 照片 (建議 3-5 張)", type=['jpg','png','jpeg'], accept_multiple_files=True)
            
            mode = st.radio("發佈模式", ["⚡ 立即發佈", "🕒 預約排程"], horizontal=True)
            
            now_tw = datetime.now(tw_tz)
            publish_time = now_tw + timedelta(minutes=30)
            
            if mode == "🕒 預約排程":
                d = st.date_input("排程日期", now_tw.date())
                t = st.time_input("排程時間", now_tw.time())
                publish_time = tw_tz.localize(datetime.combine(d, t))

        gen_btn = st.form_submit_button("🤖 生成 AI 專業文案")

    # --- 邏輯處理 ---
    if gen_btn:
        if uploaded_files:
            st.session_state['uploaded_files_data'] = [file.getvalue() for file in uploaded_files]
        else:
            st.session_state['uploaded_files_data'] = []
            
        data_payload = {
            "物件名稱": name, "總價": f"{price}萬", "單價": f"{unit_price}萬/坪",
            "建坪": f"{ping}坪", "地坪": f"{land_ping}坪", "格局": layout,
            "樓層": floor, "屋齡": age, "車位": parking, "特色": features
        }
        with st.spinner("AI 正在分析大甲行情並撰寫文中..."):
            st.session_state['current_copy'] = AISmartHelper.generate_copy(data_payload, style=copy_style)
            st.session_state['publish_mode'] = mode
            st.session_state['publish_time'] = publish_time
            st.session_state['publish_link'] = link

    # --- 第二步：確認與發佈 ---
    if st.session_state['current_copy']:
        st.markdown("---")
        final_copy = st.text_area("📝 文案確認/修改", value=st.session_state['current_copy'], height=300)
        
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🗑️ 清除重來 (發佈下一筆)"):
                st.session_state['uploaded_files_data'] = []
                st.session_state['current_copy'] = ""
                st.rerun()
                
        with col2:
            if st.button("🚀 確認發佈至 Facebook 粉絲專頁", type="primary"):
                if not st.session_state['uploaded_files_data']:
                    st.error("❌ 至少要有一張照片才能發佈喔！（請重新上傳並點擊上方生成按鈕）")
                else:
                    with st.status("正在執行自動發佈流程...", expanded=True) as status:
                        photo_ids = []
                        files_data = st.session_state['uploaded_files_data']
                        
                        status.write("🖼️ 正在處理浮水印與上傳照片...")
                        progress_bar = st.progress(0)
                        
                        for idx, file_bytes in enumerate(files_data):
                            img = AISmartHelper.add_watermark(file_bytes)
                            pid, err = upload_photo_to_fb(img)
                            if pid:
                                photo_ids.append(pid)
                            else:
                                st.error(f"第 {idx+1} 張上傳失敗: {err}")
                            progress_bar.progress((idx + 1) / len(files_data))
                        
                        if photo_ids:
                            status.write("📝 正在向 Facebook 同步資訊...")
                            p_link = st.session_state.get('publish_link', '')
                            full_msg = f"{final_copy}\n\n🔗 完整物件看這裡：{p_link}" if p_link else final_copy
                            
                            p_mode = st.session_state.get('publish_mode', '⚡ 立即發佈')
                            p_time = st.session_state.get('publish_time')
                            
                            target_time = int(p_time.timestamp()) if p_mode == "🕒 預約排程" and p_time else None
                            
                            fb_res = post_to_feed(full_msg, photo_ids, scheduled_time=target_time)
                            
                            if fb_res.status_code == 200:
                                status.update(label="✅ 發佈成功！", state="complete", expanded=False)
                                st.success(f"🎉 貼文已成功{'排程' if target_time else '發佈'}！")
                                st.balloons()
                            else:
                                st.error(f"❌ 貼文失敗：{fb_res.json()}")

# ------------------------------------------
# 分頁 2：全新的成效追蹤系統
# ------------------------------------------
with tab2:
    st.subheader("📈 粉絲專頁成效追蹤")
    st.caption("一鍵抓取近期貼文的按讚、留言與分享數，找出最熱門大甲好屋！")
    
    if st.button("🔄 立即抓取最新粉專數據", type="primary"):
        if not FB_TOKEN or not FB_PAGE_ID:
            st.error("⚠️ 找不到 Facebook 金鑰，請確認設定。")
        else:
            with st.spinner("正在與 Facebook 連線抓取資料..."):
                url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/published_posts"
                params = {
                    'fields': 'id,message,created_time,likes.summary(true),comments.summary(true),shares',
                    'access_token': FB_TOKEN,
                    'limit': 10
                }
                res = requests.get(url, params=params)
                
                if res.status_code == 200:
                    data = res.json().get('data', [])
                    if not data:
                        st.info("目前粉專上還沒有已發佈的貼文喔！")
                    else:
                        report_data = []
                        for post in data:
                            msg_preview = post.get('message', '無文字內容')[:25].replace('\n', ' ') + "..."
                            likes = post.get('likes', {}).get('summary', {}).get('total_count', 0)
                            comments = post.get('comments', {}).get('summary', {}).get('total_count', 0)
                            shares = post.get('shares', {}).get('count', 0)
                            
                            # 轉換時間格式為台灣時間閱讀習慣
                            raw_time = post.get('created_time')
                            if raw_time:
                                dt = datetime.strptime(raw_time, "%Y-%m-%dT%H:%M:%S%z")
                                formatted_time = dt.astimezone(tw_tz).strftime("%Y-%m-%d %H:%M")
                            else:
                                formatted_time = "未知時間"

                            report_data.append({
                                "發文日期": formatted_time,
                                "貼文摘要": msg_preview,
                                "👍 按讚": likes,
                                "💬 留言": comments,
                                "🔄 分享": shares
                            })
                        
                        # 顯示漂亮的資料表
                        df = pd.DataFrame(report_data)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                        st.success("✅ 數據抓取完成！")
                else:
                    st.error(f"❌ 抓取失敗：{res.json()}")

