import streamlit as st
import pandas as pd
import requests
import io
import pytz
import os
import urllib.request
import time
import textwrap
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
        st.warning("🔒 內部專用系統")
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
    def generate_copy(data_dict, style="精簡快訊", image_bytes=None, post_type="🏠 專業售屋"):
        if not GEMINI_KEY: return "⚠️ 找不到 API Key"
        
        details = "\n".join([f"{k}：{v}" for k, v in data_dict.items() if v])
        
        if post_type == "🏠 專業售屋":
            style_prompts = {
                "在地專業": "【專家分析視角】語氣穩重專業、客觀。著重於大甲區的地段發展潛力、市場行情對比、投資報酬與建築工法。讓買方覺得這是一筆『精準且保值』的決策。",
                "溫馨感性": "【說故事視角】語氣溫暖但「不廢話」。簡單點出空間帶給家人的實用性與學區/生活圈便利性，勾勒成家願景，但仍須保持房仲的專業俐落。",
                "限時急售": "【高 CP 值視角】語氣節奏快、具說服力。強調『單價優勢』、『市場稀有度』與『錯過可惜的絕佳賣點』，用市場數據或性價比來創造急迫感。",
                "精簡快訊": "【直擊痛點視角】極簡風格，完全不廢話。去除所有形容詞，只留下買方最在意的核心賣點，適合講求效率的投資客或快速瀏覽的讀者。",
                "空拍視野": "【上帝視角】語氣大氣開闊。專注描述基地面寬、地形方正、聯外道路動線與周邊無遮蔽的無敵視野，特別吸引高總價、重視大地坪或農地投資的客群。"
            }
            link_text = f"👉 **詳細資訊與更多照片請看：**\n{data_dict.get('專屬網址')}\n" if data_dict.get('專屬網址') else ""
            prompt = f"""
            你是一位台中大甲區的頂尖房仲行銷專家，目前在『翔豪不動產（有巢氏房屋大甲加盟店）』服務。
            請根據以下物件資訊，撰寫一份具備「高專業度」、且「不拖泥帶水」的 FB 貼文。
            
            【文案風格與語氣設定】: 
            {style_prompts.get(style)}
            
            【物件資訊】:
            {details}
            
            【貼文結構嚴格要求】 (請務必依照此順序排版)：
            1. 【吸睛標題】：一行呈現，必須包含物件名稱與總價，簡潔有力。
            2. 【物件基本資料】(優先顯示！)：直接將【物件資訊】轉化為清晰的條列式重點。
            3. 【專業分析與視覺亮點】(取代長篇大論)：依據設定的風格，用 3~5 點「條列式」說明物件優勢。如果有附上照片，請觀察照片並提取真實視覺亮點自然融入。
            4. 【動態標籤】：請根據物件特性，自動生成 2~3 個精準的 Hashtag。
            5. 【排版規範】：段落之間必須空行，保持畫面乾淨專業。Emoji 僅作畫龍點睛，勿過度使用。

            【結尾格式要求】 (請原封不動放在文案最後):
            ---
            {link_text}🏠 **翔豪不動產 - 有巢氏房屋台中大甲店 (孔子廟對面)**
            📞 **賞屋專線：04-26888050**
            📍 **大甲區文武路99號**
            📝 **經紀業特許字號:府地價字09901380561**
            📝 **(103)中市經紀字第01306號**
            #大甲房產 #大甲買屋 #有巢氏房屋 #台中房地產
            """
        else:
            prompt = f"""
            你是一位台中大甲區的頂尖房仲，目前在『翔豪不動產（有巢氏房屋大甲加盟店）』服務。
            請根據以下資訊，寫一篇「接地氣、有溫度」的在地生活圈 FB 貼文，用來圈粉和建立親和力。

            【主題/地點】：{data_dict.get('主題/地點')}
            【關鍵字/心得】：{data_dict.get('關鍵字')}

            【撰寫要求】：
            1. 語氣要像在地人推薦朋友一樣自然、熱情，完全不要有賣房子的推銷感。
            2. 觀察附上的照片（若有），將照片中的視覺細節生動地寫入文章中。
            3. 結尾用「一句話」巧妙自然地帶出你的身分，例如：「吃飽喝足，下午繼續去帶客戶看大甲好房！」。
            4. 結尾必須包含以下聯絡資訊：
            
            ---
            🏠 **翔豪不動產 - 有巢氏房屋台中大甲店 (孔子廟對面)**
            📞 **在地顧問專線：04-26888050**
            📍 **大甲區文武路99號**
            📝 **經紀業特許字號:府地價字09901380561**
            📝 **(103)中市經紀字第01306號**
            #大甲美食 #大甲景點 #大甲房產 #有巢氏房屋台中大甲店 #大甲在地推薦
            """

        models_to_try = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-pro"]
        last_error = ""
        for model_name in models_to_try:
            try:
                return get_cached_ai_response(prompt, model_name, image_bytes)
            except Exception as e:
                last_error = str(e)
                time.sleep(2)
                continue
        return f"❌ 生成失敗：{last_error}"

    @staticmethod
    def generate_ad_advice(post_text):
        if not GEMINI_KEY: return "⚠️ 找不到 API Key，無法生成建議"
        prompt = f"""
        你是一位 Meta (Facebook) 廣告投放專家。
        以下是一篇在大甲區表現非常好的房仲/在地貼文，請幫我分析並給出「臉書下廣告的具體設定建議」。
        
        【貼文內容】：
        {post_text}
        
        【輸出格式要求 (請簡潔條列)】：
        🎯 **建議鎖定年齡**：(例如 30-45歲)
        📍 **建議投放地區**：(以大甲為中心，要不要包到清水、苑裡等周邊？)
        🏷️ **建議興趣標籤**：(給出 3~5 個精準的 Meta 興趣標籤)
        💡 **專家一句話提醒**：(給出一句這篇廣告該注意的重點，例如預算建議或受眾心理)
        """
        try:
            return get_cached_ai_response(prompt, "gemini-1.5-flash")
        except Exception:
            return "無法生成廣告建議，請稍後再試。"

    # 🔧 【修改點】：讓靈感大腦強制輸出 [標題] 與 [內文] 兩種格式
    @staticmethod
    def generate_daily_inspiration(topic_type, additional_notes=""):
        if not GEMINI_KEY: return "⚠️ 找不到 API Key"
        prompt = f"""
        你是一位台中大甲區的資深房產行銷專家，目前在『翔豪不動產（有巢氏房屋大甲加盟店）』服務。
        請針對以下主題：【{topic_type}】，撰寫一篇能吸引大甲在地鄉親互動的 Facebook 貼文。
        
        【重點提示與補充資訊】：
        {additional_notes if additional_notes else '無特定補充，請發揮在地房產專家的專業知識自由創作。'}

        【嚴格輸出格式】 (請務必使用特定的分隔符號)：
        [圖文大標題]
        (請在這裡寫一句 15 個字以內、非常吸睛的標題，絕對不能超過 15 個字，這句話將用來做成圖片)
        [貼文內文]
        (請在這裡寫貼文內文。若主題是『在地新聞』請聚焦近期大甲大小事；若是『房產知識』請用白話文解釋；若是『動態』請給出專業建議。適當使用 Emoji，排版乾淨。)
        
        ---
        🏠 **翔豪不動產 - 有巢氏房屋台中大甲店 (孔子廟對面)**
        📞 **在地顧問專線：04-26888050**
        📍 **大甲區文武路99號**
        📝 **經紀業特許字號:府地價字09901380561**
        📝 **(103)中市經紀字第01306號**
        """
        try:
            return get_cached_ai_response(prompt, "gemini-2.5-flash")
        except Exception as e:
            return f"❌ 靈感生成失敗：{str(e)}"

    # 🔧 【新增功能】：動態生成臉書 1080x1080 圖文卡片
    @staticmethod
    def generate_social_card(title_text, theme_type="大甲在地新聞"):
        # 下載或讀取字體
        font_filename = "NotoSansCJKtc-Regular.otf"
        if not os.path.exists(font_filename):
            try:
                urllib.request.urlretrieve("https://raw.githubusercontent.com/googlefonts/noto-cjk/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf", font_filename)
            except: pass 

        # 建立 1080x1080 正方形背景
        width, height = 1080, 1080
        
        # 根據主題設定底色
        if theme_type == "大甲在地新聞":
            bg_color = (25, 60, 95)     # 深藍專業感
        elif theme_type == "房產知識通":
            bg_color = (30, 90, 70)     # 有巢氏綠色系
        else:
            bg_color = (130, 45, 30)    # 趨勢動態橘紅色

        img = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(img)

        # 畫個簡單的白色邊框增加質感
        border_margin = 40
        draw.rectangle(
            [border_margin, border_margin, width - border_margin, height - border_margin],
            outline=(255, 255, 255), width=8
        )

        try:
            font_title = ImageFont.truetype(font_filename, 90)
            font_subtitle = ImageFont.truetype(font_filename, 45)
        except:
            font_title = ImageFont.load_default()
            font_subtitle = ImageFont.load_default()

        # 自動換行標題文字 (每行約 8~10 字)
        wrapped_text = textwrap.fill(title_text, width=10)
        
        # 繪製置中文字
        text_bbox = draw.textbbox((0, 0), wrapped_text, font=font_title)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]
        
        x = (width - text_w) / 2
        y = (height - text_h) / 2 - 50  # 稍微偏上留空間給 Logo
        
        # 加點文字陰影
        draw.multiline_text((x+5, y+5), wrapped_text, font=font_title, fill=(0,0,0,150), align="center")
        draw.multiline_text((x, y), wrapped_text, font=font_title, fill=(255,255,255), align="center")

        # 底部加上店家資訊
        brand_text = "🏠 翔豪不動產 | 有巢氏房屋台中大甲店"
        bbox_brand = draw.textbbox((0, 0), brand_text, font=font_subtitle)
        brand_w = bbox_brand[2] - bbox_brand[0]
        draw.text(((width - brand_w) / 2, height - 150), brand_text, font=font_subtitle, fill=(200, 220, 200))

        # 將 Image 轉為 Bytes
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()

    @staticmethod
    def add_watermark(image_bytes, text="翔豪不動產 - 有巢氏台中大甲店", position_type="右下角", color_theme="專屬綠 (推薦)"):
        font_filename = "NotoSansCJKtc-Regular.otf"
        if not os.path.exists(font_filename):
            try:
                urllib.request.urlretrieve("https://raw.githubusercontent.com/googlefonts/noto-cjk/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf", font_filename)
            except: pass 
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img = ImageOps.exif_transpose(img)
            img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            img = img.convert("RGBA")
            txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt_layer)
            w, h = img.size
            
            try: font = ImageFont.truetype(font_filename, int(h / 16))
            except: font = ImageFont.load_default()
            
            margin = int(w * 0.03)
            
            if position_type == "左下角": 
                pos = (margin, h - margin)
                anchor_align = "ld"
            elif position_type == "置中": 
                pos = (w // 2, h // 2)
                anchor_align = "mm"
            else: 
                pos = (w - margin, h - margin)
                anchor_align = "rd"
            
            if color_theme == "專屬綠 (推薦)":
                main_color, stroke_color = (0, 153, 76, 240), (255, 255, 255, 255) 
            elif color_theme == "亮眼黃":
                main_color, stroke_color = (255, 215, 0, 240), (30, 30, 30, 255)    
            else: 
                main_color, stroke_color = (255, 255, 255, 240), (30, 30, 30, 255)    

            draw.text((pos[0]+3, pos[1]+3), text, font=font, fill=(0, 0, 0, 150), anchor=anchor_align)
            draw.text(pos, text, font=font, fill=main_color, stroke_width=3, stroke_fill=stroke_color, anchor=anchor_align)
            return Image.alpha_composite(img, txt_layer).convert("RGB")
        except: return None

# ==========================================
# 4. FB API 溝通層
# ==========================================
def upload_photo_to_fb(image_obj):
    if not image_obj: return None, "Image processing failed"
    buf = io.BytesIO()
    image_obj.save(buf, format='JPEG', quality=90)
    buf.seek(0)
    res = requests.post(f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}/photos", data={'published': 'false', 'access_token': FB_TOKEN}, files={'source': buf})
    return res.json().get('id'), res.json().get('error')

def post_to_feed(message, photo_ids, scheduled_time=None):
    payload = {'message': message, 'access_token': FB_TOKEN}
    if scheduled_time:
        payload['published'] = 'false'
        payload['scheduled_publish_time'] = scheduled_time
    for i, p_id in enumerate(photo_ids):
        payload[f'attached_media[{i}]'] = f'{{"media_fbid": "{p_id}"}}'
    return requests.post(f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}/feed", data=payload)

def post_video_to_fb(video_bytes, message, scheduled_time=None):
    url = f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}/videos"
    payload = {'description': message, 'access_token': FB_TOKEN}
    if scheduled_time:
        payload['published'] = 'false'
        payload['scheduled_publish_time'] = scheduled_time

    files = {'source': ('veo_video.mp4', video_bytes, 'video/mp4')}
    return requests.post(url, data=payload, files=files, timeout=120)

def delete_fb_post(post_id):
    return requests.delete(f"https://graph.facebook.com/v25.0/{post_id}", params={'access_token': FB_TOKEN})

def update_fb_post(post_id, new_message):
    return requests.post(f"https://graph.facebook.com/v25.0/{post_id}", data={'message': new_message, 'access_token': FB_TOKEN})

def reset_app_state():
    st.session_state['generated_posts'] = []
    st.session_state['ordered_images'] = []
    st.session_state['processed_file_names'] = []
    if 'uploaded_video' in st.session_state:
        del st.session_state['uploaded_video']
    st.rerun()

# ==========================================
# 5. 主介面 UI
# ==========================================
st.title("🚀 發文小幫手 Master Pro")
check_fb_token_health() 

if 'generated_posts' not in st.session_state: st.session_state['generated_posts'] = []
if 'ordered_images' not in st.session_state: st.session_state['ordered_images'] = []
if 'processed_file_names' not in st.session_state: st.session_state['processed_file_names'] = []
if 'watermark_pos' not in st.session_state: st.session_state['watermark_pos'] = "右下角"
if 'watermark_color' not in st.session_state: st.session_state['watermark_color'] = "專屬綠 (推薦)"

tab1, tab2, tab3, tab4 = st.tabs([
    "🚀 AI 自動發文與排程", 
    "📊 粉專成效儀表板 (含廣告指揮所)", 
    "🗓️ 預定排程管理", 
    "🤖 靈感大腦與動態製圖"
])

with tab1:
    post_type = st.radio("📝 選擇發文類型", ["🏠 專業售屋", "🍜 在地生活圈"], horizontal=True)
    st.markdown("---")
    
    m_col1, m_col2, m_col3 = st.columns(3)
    
    if post_type == "🏠 專業售屋":
        with m_col1:
            st.subheader("📝 核心資訊")
            name = st.text_input("🏠 物件名稱*", placeholder="例：大甲鎮瀾商圈美墅")
            address = st.text_input("📍 物件地址/路段", placeholder="例：大甲區中山路一段")
            price = st.number_input("💰 總價 (萬)", min_value=0, step=10, value=1200)
            ping = st.number_input("📐 建坪 (坪)", min_value=0.0, step=0.1, value=45.0)
            land_ping = st.number_input("🌲 地坪 (坪)", min_value=0.0, step=0.1, value=25.0)

        with m_col2:
            st.subheader("📏 規格細節")
            floor = st.text_input("🏢 樓層", placeholder="例：3樓 / 總樓層10樓")
            layout = st.text_input("🚪 格局", placeholder="如: 4房2廳3衛")
            
            parking = st.selectbox("🚗 車位", ["無", "自有車庫", "坡道平面", "機械上層車位", "機械下層車位", "門口停車"])
            
            link = st.text_input("🔗 物件專屬網址", placeholder="大甲店官網首頁")
            features = st.text_area("✨ 物件特色", placeholder="近學區、採光通風好...", height=70)
            
            uploaded_files = st.file_uploader("📸 照片上傳 (支援多次補傳、下方可刪除排序)", type=['jpg','png','jpeg'], accept_multiple_files=True)
            
    elif post_type == "🍜 在地生活圈":
        with m_col1:
            st.subheader("🍜 分享主題")
            life_title = st.text_input("📍 主題/地點*", placeholder="例：鎮瀾宮旁無名粉腸")
            life_keywords = st.text_area("✨ 關鍵字或心得", placeholder="例：排隊、從小吃到大...", height=120)
            
        with m_col2:
            st.subheader("📸 照片上傳")
            st.info("附上美食或風景照片，AI 會觀察寫得更生動喔！")
            uploaded_files = st.file_uploader("上傳生活圈照片 (支援多次補傳)", type=['jpg','png','jpeg'], accept_multiple_files=True)
            
    with m_col3:
        st.subheader("📅 多風格排程設定")
        if post_type == "🏠 專業售屋":
            selected_styles = st.multiselect("🎨 文案風格", ["在地專業", "溫馨感性", "限時急售", "精簡快訊", "空拍視野"], default=["精簡快訊"])
        else:
            selected_styles = ["在地生活"]
            st.info("🎨 當前風格：親和力在地生活圈")
        
        mode = st.radio("發佈模式", ["⚡ 立即發佈", "📅 自訂多天排程"], horizontal=True)
        time_options = [f"{h:02d}:{m:02d}" for h in range(7, 22) for m in (0, 30) if not (h==21 and m==30)]
        default_idx = time_options.index("18:00") if "18:00" in time_options else 0
        
        post_schedules = []
        now = datetime.now(tw_tz)
        
        if mode == "📅 自訂多天排程":
            num_posts = st.slider("📌 預計排程幾篇貼文？", 1, 10, 1 if post_type == "🍜 在地生活圈" else 3)
            for i in range(num_posts):
                col_d, col_t = st.columns(2)
                with col_d: d = st.date_input(f"🗓️ 第 {i+1} 篇日期", now.date() + timedelta(days=i*2), key=f"d_{i}")
                with col_t: t_str = st.selectbox(f"⏰ 時間", time_options, index=default_idx, key=f"t_{i}")
                post_schedules.append(tw_tz.localize(datetime.combine(d, datetime.strptime(t_str, "%H:%M").time())))
        else:
            post_schedules.append(now + timedelta(minutes=15))

    if uploaded_files:
        for f in uploaded_files:
            if f.name not in st.session_state['processed_file_names']:
                st.session_state['ordered_images'].append(f.getvalue())
                st.session_state['processed_file_names'].append(f.name)

    st.markdown("---")
    st.subheader("🎥 短影音上傳 (Reels 格式)")
    st.info("💡 系統發佈優先級：若同時有「照片」與「影片」，系統發佈時將強制發佈【影片】，無視照片排序與浮水印。")
    uploaded_video = st.file_uploader("上傳 AI 生成的 30 秒內短影音 (支援 mp4, mov)", type=['mp4', 'mov'])
    
    if uploaded_video:
        st.session_state['uploaded_video'] = uploaded_video.getvalue()
    elif 'uploaded_video' in st.session_state:
        del st.session_state['uploaded_video']

    if st.session_state['ordered_images']:
        st.markdown("---")
        st.subheader("🖼️ 照片排序、刪除與浮水印設定")
        col_pos, col_color = st.columns(2)
        with col_pos: watermark_pos = st.radio("📍 位置", ["右下角", "左下角", "置中"], horizontal=True, index=["右下角", "左下角", "置中"].index(st.session_state['watermark_pos']))
        with col_color: watermark_color = st.radio("🎨 顏色", ["經典白", "專屬綠 (推薦)", "亮眼黃"], horizontal=True, index=["經典白", "專屬綠 (推薦)", "亮眼黃"].index(st.session_state['watermark_color']))
            
        st.session_state['watermark_pos'] = watermark_pos
        st.session_state['watermark_color'] = watermark_color
        
        cols_per_row = 4
        num_imgs = len(st.session_state['ordered_images'])
        
        for row_start in range(0, num_imgs, cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                idx = row_start + j
                if idx < num_imgs:
                    img_bytes = st.session_state['ordered_images'][idx]
                    preview_img = AISmartHelper.add_watermark(image_bytes=img_bytes, text="翔豪不動產 - 有巢氏台中大甲店", position_type=watermark_pos, color_theme=watermark_color)
                    
                    with cols[j]:
                        if preview_img: st.image(preview_img, caption=f"發佈順序 {idx+1}", use_container_width=True)
                        
                        btn_c1, btn_c2, btn_c3 = st.columns([1, 1, 1])
                        with btn_c1:
                            if idx > 0 and st.button("⬅️", key=f"l_{idx}"):
                                st.session_state['ordered_images'][idx], st.session_state['ordered_images'][idx-1] = st.session_state['ordered_images'][idx-1], st.session_state['ordered_images'][idx]
                                st.rerun()
                        with btn_c2:
                            if st.button("🗑️", key=f"del_{idx}"):
                                st.session_state['ordered_images'].pop(idx)
                                st.rerun()
                        with btn_c3:
                            if idx < num_imgs - 1 and st.button("➡️", key=f"r_{idx}"):
                                st.session_state['ordered_images'][idx], st.session_state['ordered_images'][idx+1] = st.session_state['ordered_images'][idx+1], st.session_state['ordered_images'][idx]
                                st.rerun()

    st.markdown("---")
    gen_btn = st.button("🤖 啟動 AI 批量生成", type="primary", use_container_width=True)

    if gen_btn:
        if post_type == "🏠 專業售屋":
            if not selected_styles: st.error("❌ 請至少選擇一種文案風格！"); st.stop()
            if not name: st.error("❌ 請填寫物件名稱！"); st.stop()
            final_link = link if link.strip() else "https://shop.yungching.com.tw/0426888050"
            data_payload = {"物件名稱": name, "地址/路段": address, "總價": f"{price}萬", "建坪": f"{ping}坪", "地坪": f"{land_ping}坪", "樓層": floor, "格局": layout, "車位": parking, "專屬網址": final_link, "特色": features}
        elif post_type == "🍜 在地生活圈":
            if not life_title: st.error("❌ 請填寫生活圈分享的「主題/地點」！"); st.stop()
            data_payload = {"主題/地點": life_title, "關鍵字": life_keywords}
            
        st.session_state['generated_posts'] = []
        now = datetime.now(tw_tz)
        first_image_bytes = st.session_state['ordered_images'][0] if st.session_state['ordered_images'] else None
        progress_text = st.empty()
        
        for i, target_dt in enumerate(post_schedules):
            target_dt = max(target_dt, datetime.now(tw_tz) + timedelta(minutes=15))
            current_style = selected_styles[i % len(selected_styles)]
            progress_text.info(f"⏳ 正在生成第 {i+1}/{len(post_schedules)} 篇貼文 (類型：{post_type})...")
            
            copy_text = AISmartHelper.generate_copy(data_dict=data_payload, style=current_style, image_bytes=first_image_bytes, post_type=post_type)
            st.session_state['generated_posts'].append({"發文時間": target_dt, "風格": "親和力推薦" if post_type == "🍜 在地生活圈" else current_style, "文案": copy_text})
        
        progress_text.success("✅ AI 生成完畢！請在下方預覽確認。")

    if st.session_state['generated_posts']:
        st.markdown("---")
        st.subheader("👀 貼文預覽與修改")
        
        for idx, post in enumerate(st.session_state['generated_posts']):
            with st.expander(f"第 {idx+1} 篇 ➔ 預計發佈：{post['發文時間'].strftime('%Y-%m-%d %H:%M')} (風格：{post['風格']})", expanded=(idx==0)):
                st.session_state['generated_posts'][idx]['文案'] = st.text_area("修改文案", value=post['文案'], height=250, key=f"text_{idx}")

        col_submit, col_reset = st.columns([3, 1])
        with col_submit:
            if st.button("🚀 確認無誤，全部排程至 Facebook", type="primary", use_container_width=True):
                has_images = len(st.session_state.get('ordered_images', [])) > 0
                has_video = 'uploaded_video' in st.session_state

                if not has_images and not has_video:
                    st.error("❌ 至少要上傳一張照片或一支影片才能發佈喔！")
                else:
                    with st.status("正在將任務傳送至 Facebook 系統...", expanded=True) as status:
                        success_count = 0
                        total_imgs = len(st.session_state.get('ordered_images', []))

                        for post_idx, post in enumerate(st.session_state['generated_posts']):
                            st.write(f"🔄 準備處理第 {post_idx+1} 篇貼文...")
                            
                            photo_ids = []
                            if not has_video:
                                for idx, file_bytes in enumerate(st.session_state['ordered_images']):
                                    st.write(f"  📸 為第 {post_idx+1} 篇上傳照片 ({idx+1}/{total_imgs})...")
                                    img = AISmartHelper.add_watermark(image_bytes=file_bytes, text="翔豪不動產 - 有巢氏台中大甲店", position_type=st.session_state['watermark_pos'], color_theme=st.session_state['watermark_color'])
                                    pid, err = upload_photo_to_fb(img)
                                    if pid: photo_ids.append(pid)
                                    time.sleep(1)
                                
                                if not photo_ids:
                                    st.error(f"❌ 第 {post_idx+1} 篇照片上傳失敗，跳過此篇。")
                                    continue
                                    
                                st.write("  ⏳ 等待 FB 伺服器同步圖片檔案 (約 5 秒)...")
                                time.sleep(5) 

                            max_retries = 4
                            for attempt in range(max_retries):
                                t_stamp = int(post['發文時間'].timestamp()) if mode == "📅 自訂多天排程" else None
                                if t_stamp:
                                    current_ts = int(datetime.now(tw_tz).timestamp())
                                    if t_stamp < current_ts + 600: 
                                        t_stamp = current_ts + 900 
                                        st.toast(f"⏳ 自動修正：貼文時間過於接近現在，已自動順延！")

                                if has_video:
                                    if attempt == 0: st.write("  🎥 正在上傳短影音至 Facebook...")
                                    fb_res = post_video_to_fb(st.session_state['uploaded_video'], post['文案'], scheduled_time=t_stamp)
                                else:
                                    fb_res = post_to_feed(post['文案'], photo_ids, scheduled_time=t_stamp)
                                
                                if fb_res.status_code == 200: 
                                    success_count += 1
                                    st.write(f"  ✅ 第 {post_idx+1} 篇排程成功！")
                                    break
                                else: 
                                    err_data = fb_res.json()
                                    if (err_data.get('error', {}).get('is_transient', False) or err_data.get('error', {}).get('code') == 2) and attempt < max_retries - 1:
                                        time.sleep(3 * (attempt + 1)) 
                                    else:
                                        st.error(f"❌ 第 {post_idx+1} 篇排程失敗：{err_data}")
                                        break

                        if success_count == len(st.session_state['generated_posts']):
                            status.update(label="✅ 所有任務處理完畢！", state="complete")
                            st.success(f"🎉 成功排程了 {success_count} 篇貼文！")
                            st.balloons()
                            st.session_state['post_success'] = True
                        else:
                            status.update(label="⚠️ 部分任務完成，請檢查上方錯誤訊息。", state="error")

        with col_reset:
            if st.session_state.get('post_success', False):
                if st.button("✨ 完成並建立下一筆", use_container_width=True):
                    st.session_state['post_success'] = False
                    reset_app_state()

# ==========================================
# 6. Tab 2: 粉專成效儀表板
# ==========================================
with tab2:
    st.header("📈 粉絲專頁營運戰情室")
    if st.button("🔄 撈取最新營運數據"):
        if not FB_PAGE_ID or not FB_TOKEN:
            st.error("⚠️ 缺少 FB_PAGE_ID 或 FB_TOKEN 設定。")
        else:
            with st.spinner("正在與 Facebook 連線，解析近期營運與潛力爆款中..."):
                api_base = f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}"
                try:
                    page_data = requests.get(api_base, params={'fields': 'fan_count,followers_count,name', 'access_token': FB_TOKEN}).json()
                    if 'error' not in page_data:
                        st.success(f"✅ 成功連線至粉專：**{page_data.get('name')}**")
                        met_col1, met_col2 = st.columns(2)
                        met_col1.metric("👥 總粉絲專頁讚數", f"{int(page_data.get('fan_count', 0)):,}")
                        met_col2.metric("🔔 總追蹤人數", f"{int(page_data.get('followers_count', 0)):,}")
                        st.markdown("---")
                        
                        posts_res = requests.get(f"{api_base}/published_posts", params={'fields': 'id,created_time,message,permalink_url,likes.summary(true),comments.summary(true)', 'limit': 15, 'access_token': FB_TOKEN}).json()
                        
                        has_eng = True
                        if 'error' in posts_res and posts_res['error'].get('code') in [10, 100]:
                            has_eng = False
                            posts_res = requests.get(f"{api_base}/published_posts", params={'fields': 'id,created_time,message,permalink_url', 'limit': 15, 'access_token': FB_TOKEN}).json()

                        posts = posts_res.get('data', [])
                        if posts:
                            parsed_posts = []
                            total_engagement = 0
                            for p in posts:
                                try:
                                    c_time = datetime.strptime(p['created_time'], '%Y-%m-%dT%H:%M:%S%z').astimezone(tw_tz)
                                    lks = p.get('likes', {}).get('summary', {}).get('total_count', 0) if has_eng else 0
                                    cms = p.get('comments', {}).get('summary', {}).get('total_count', 0) if has_eng else 0
                                    total_engagement += (lks + cms)
                                    parsed_posts.append({'time': c_time, 'message': p.get('message', ''), 'url': p.get('permalink_url', '#'), 'likes': lks, 'comments': cms})
                                except: continue
                            
                            st.subheader("📝 近期發文軌跡 (最新 15 篇)")
                            for p in parsed_posts:
                                with st.container():
                                    col_time, col_msg, col_eng, col_link = st.columns([2, 4, 1.5, 1])
                                    with col_time: st.markdown(f"**🗓️ {p['time'].strftime('%Y-%m-%d %H:%M')}**")
                                    with col_msg: st.text(p['message'][:80].replace('\n', ' ') + "...")
                                    with col_eng: st.markdown(f"👍 {p['likes']} | 💬 {p['comments']}")
                                    with col_link: st.markdown(f"[🔗 看貼文]({p['url']})")
                                st.divider()
                except Exception as e: st.error(f"錯誤：{e}")

# ==========================================
# 7. Tab 3: 預定排程管理
# ==========================================
with tab3:
    st.header("🗓️ 排程貼文管理")
    if st.button("🔄 重新讀取排程清單"): st.rerun()
    if FB_PAGE_ID and FB_TOKEN:
        try:
            res = requests.get(f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}/scheduled_posts", params={'fields': 'id,message,scheduled_publish_time', 'access_token': FB_TOKEN}).json()
            if 'error' not in res:
                scheduled_posts = res.get('data', [])
                if scheduled_posts:
                    st.success(f"共有 **{len(scheduled_posts)}** 篇排程貼文：")
                    for p in scheduled_posts:
                        p_id, msg = p['id'], p.get('message', '')
                        s_time_val = p.get('scheduled_publish_time')
                        s_time = datetime.fromtimestamp(s_time_val, tw_tz).strftime('%Y-%m-%d %H:%M') if isinstance(s_time_val, int) else str(s_time_val)
                        with st.expander(f"⏰ 預計發佈時間：{s_time}"):
                            new_msg = st.text_area("修改貼文內容", value=msg, height=200, key=f"edit_{p_id}")
                            c1, c2 = st.columns(2)
                            with c1:
                                if st.button("💾 儲存修改", key=f"save_{p_id}", use_container_width=True):
                                    if update_fb_post(p_id, new_msg).status_code == 200: st.success("✅ 修改成功！"); time.sleep(1); st.rerun()
                            with c2:
                                if st.button("🗑️ 刪除排程", key=f"del_{p_id}", type="primary", use_container_width=True):
                                    if delete_fb_post(p_id).status_code == 200: st.success("✅ 刪除成功！"); time.sleep(1); st.rerun()
                else: st.info("目前沒有排程貼文。")
        except: pass

# ==========================================
# 8. Tab 4: 靈感大腦與動態製圖 (專屬 gemini-2.5-flash)
# ==========================================
with tab4:
    st.header("🤖 靈感大腦與自動圖文產生器")
    st.markdown("在此生成的文章將**獨家啟用 Gemini 2.5 Flash**。系統會自動抓取金句，繪製成高質感的 Facebook 專屬圖卡，讓您無需再煩惱找圖！")
    
    col_brain, col_preview = st.columns([1, 1])
    
    with col_brain:
        st.subheader("💡 第一步：選擇主題並產出內容")
        topic_type = st.selectbox("請選擇今日想發佈的主題類型：", ["大甲在地新聞", "房產知識通", "當日房市動態"])
        additional_notes = st.text_input("📝 補充關鍵字 (選填)", placeholder="例如：大甲體育場旁、房地合一稅...")
        
        if st.button("✨ 立即生成靈感文案與字卡", type="primary", use_container_width=True):
            with st.spinner(f"正在呼叫高階 AI 撰寫文案與繪製圖卡..."):
                raw_result = AISmartHelper.generate_daily_inspiration(topic_type, additional_notes)
                
                # 解析 AI 輸出的 [圖文大標題] 與 [貼文內文]
                title_part = "大甲房市快訊"
                content_part = raw_result
                
                if "[圖文大標題]" in raw_result and "[貼文內文]" in raw_result:
                    parts = raw_result.split("[貼文內文]")
                    title_section = parts[0].replace("[圖文大標題]", "").strip()
                    # 清理可能的多餘空行
                    title_part = [line for line in title_section.split("\n") if line.strip()][0][:15] 
                    content_part = parts[1].strip()
                
                # 存入 Session 供畫面顯示
                st.session_state['temp_title'] = title_part
                st.session_state['temp_content'] = content_part
                
                # 自動生成圖卡
                img_bytes = AISmartHelper.generate_social_card(title_part, topic_type)
                st.session_state['temp_image_bytes'] = img_bytes
                
    with col_preview:
        if 'temp_content' in st.session_state:
            st.subheader("🖼️ 第二步：預覽與發佈")
            
            # 顯示自動生成的圖片
            st.image(st.session_state['temp_image_bytes'], caption=f"自動生成的金句圖卡 ({st.session_state['temp_title']})", use_container_width=True)
            
            st.markdown("**📝 生成的文案 (可自行微調)：**")
            st.session_state['temp_content'] = st.text_area("文案內容", value=st.session_state['temp_content'], height=200, label_visibility="collapsed")
            
            # 核心連動防呆按鈕
            if st.button("🚀 一鍵帶入到【Tab 1 發文排程區】", type="primary", use_container_width=True):
                # 1. 把產生的字卡存入待發佈照片陣列
                if 'ordered_images' not in st.session_state:
                    st.session_state['ordered_images'] = []
                st.session_state['ordered_images'] = [st.session_state['temp_image_bytes']]
                
                # 2. 自動在 Tab 1 生成一筆排程任務 (預設 15 分鐘後發)
                st.session_state['generated_posts'] = [{
                    "發文時間": datetime.now(tw_tz) + timedelta(minutes=15),
                    "風格": "靈感大腦專屬",
                    "文案": st.session_state['temp_content']
                }]
                
                st.success("✅ 已成功匯入！請切換至【Tab 1：AI 自動發文與排程】的最下方，確認時間後點擊「全部排程至 Facebook」即可完成發布！")
                st.balloons()
