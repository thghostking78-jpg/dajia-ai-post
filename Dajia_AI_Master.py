import streamlit as st
import pandas as pd
import requests
import io
import pytz
import os
import urllib.request
import time
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

        models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]
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
            return get_cached_ai_response(prompt, "gemini-2.5-flash")
        except Exception:
            return "無法生成廣告建議，請稍後再試。"

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

def delete_fb_post(post_id):
    return requests.delete(f"https://graph.facebook.com/v25.0/{post_id}", params={'access_token': FB_TOKEN})

def update_fb_post(post_id, new_message):
    return requests.post(f"https://graph.facebook.com/v25.0/{post_id}", data={'message': new_message, 'access_token': FB_TOKEN})

def reset_app_state():
    st.session_state['generated_posts'] = []
    st.session_state['ordered_images'] = []
    st.session_state['processed_file_names'] = []
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

tab1, tab2, tab3 = st.tabs(["🚀 AI 自動發文與排程", "📊 粉專成效儀表板 (含廣告指揮所)", "🗓️ 預定排程管理"])

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
            # ==========================================
            # 🌟 最新的排程邏輯：為每一篇貼文「獨立」上傳圖片，避免 ID 重複使用導致錯誤！
            # ==========================================
            if st.button("🚀 確認無誤，全部排程至 Facebook", type="primary", use_container_width=True):
                if not st.session_state['ordered_images']:
                    st.error("❌ 至少要有一張照片才能發佈喔！")
                else:
                    with st.status("正在將任務傳送至 Facebook 系統...", expanded=True) as status:
                        success_count = 0
                        total_imgs = len(st.session_state['ordered_images'])

                        for post_idx, post in enumerate(st.session_state['generated_posts']):
                            st.write(f"🔄 準備處理第 {post_idx+1} 篇貼文...")
                            
                            # 🌟 核心修正：把「上傳照片」移到迴圈內！每篇貼文都擁有自己的一批全新 photo_id
                            photo_ids = []
                            for idx, file_bytes in enumerate(st.session_state['ordered_images']):
                                st.write(f"  📸 為第 {post_idx+1} 篇上傳照片 ({idx+1}/{total_imgs})...")
                                img = AISmartHelper.add_watermark(image_bytes=file_bytes, text="翔豪不動產 - 有巢氏台中大甲店", position_type=st.session_state['watermark_pos'], color_theme=st.session_state['watermark_color'])
                                pid, err = upload_photo_to_fb(img)
                                if pid:
                                    photo_ids.append(pid)
                                time.sleep(1) # 上傳緩衝
                            
                            if not photo_ids:
                                st.error(f"❌ 第 {post_idx+1} 篇照片上傳失敗，跳過此篇。")
                                continue
                                
                            st.write("  ⏳ 等待 FB 伺服器同步圖片檔案 (約 5 秒)...")
                            time.sleep(5) 

                            # 🌟 升級防護 3：階梯式重試機制
                            max_retries = 4
                            for attempt in range(max_retries):
                                t_stamp = int(post['發文時間'].timestamp()) if mode == "📅 自訂多天排程" else None
                                if t_stamp:
                                    current_ts = int(datetime.now(tw_tz).timestamp())
                                    if t_stamp < current_ts + 600: 
                                        t_stamp = current_ts + 900 
                                        st.toast(f"⏳ 自動修正：貼文時間過於接近現在，已自動順延！")

                                fb_res = post_to_feed(post['文案'], photo_ids, scheduled_time=t_stamp)
                                
                                if fb_res.status_code == 200: 
                                    success_count += 1
                                    st.write(f"  ✅ 第 {post_idx+1} 篇排程成功！")
                                    break
                                else: 
                                    err_data = fb_res.json()
                                    err_is_transient = err_data.get('error', {}).get('is_transient', False)
                                    err_code = err_data.get('error', {}).get('code')
                                    
                                    if (err_is_transient or err_code == 2) and attempt < max_retries - 1:
                                        wait_time = 3 * (attempt + 1)
                                        st.toast(f"⚠️ FB 伺服器忙碌中，{wait_time} 秒後自動進行第 {attempt+2} 次重試...")
                                        time.sleep(wait_time) 
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
# 6. Tab 2: 粉專成效儀表板 (🌟 廣告司令部升級版)
# ==========================================
with tab2:
    st.header("📈 粉絲專頁營運戰情室")
    st.markdown("追蹤您的粉專成長軌跡。當發現「高互動爆款」時，系統會自動提供廣告投放建議！")
    
    if st.button("🔄 撈取最新營運數據"):
        if not FB_PAGE_ID or not FB_TOKEN:
            st.error("⚠️ 缺少 FB_PAGE_ID 或 FB_TOKEN 設定。")
        else:
            with st.spinner("正在與 Facebook 連線，解析近期營運與潛力爆款中..."):
                api_base = f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}"
                
                try:
                    page_data = requests.get(api_base, params={'fields': 'fan_count,followers_count,name', 'access_token': FB_TOKEN}).json()
                    
                    if 'error' in page_data:
                        st.error(f"❌ 無法撈取粉專資料：{page_data['error']['message']}")
                    else:
                        st.success(f"✅ 成功連線至粉專：**{page_data.get('name', '有巢氏台中大甲店')}**")
                        met_col1, met_col2 = st.columns(2)
                        met_col1.metric("👥 總粉絲專頁讚數", f"{int(page_data.get('fan_count', 0)):,}")
                        met_col2.metric("🔔 總追蹤人數", f"{int(page_data.get('followers_count', 0)):,}")
                        st.markdown("---")
                        
                        advanced_params = {
                            'fields': 'id,created_time,message,permalink_url,likes.summary(true),comments.summary(true)',
                            'limit': 15,
                            'access_token': FB_TOKEN
                        }
                        
                        posts_res = requests.get(f"{api_base}/published_posts", params=advanced_params)
                        posts_data = posts_res.json()
                        
                        has_engagement_permission = True
                        if 'error' in posts_data:
                            if posts_data['error'].get('code') in [10, 100]:
                                has_engagement_permission = False
                                st.warning("⚠️ 目前的 FB Token 缺少讀取按讚與留言的權限 (pages_read_engagement)，無法啟用「爆款偵測器」。已自動切換為基本模式。")
                                posts_data = requests.get(f"{api_base}/published_posts", params={'fields': 'id,created_time,message,permalink_url', 'limit': 15, 'access_token': FB_TOKEN}).json()
                            else:
                                st.error(f"❌ 獲取貼文失敗：{posts_data['error']['message']}")
                                posts_data = {'data': []}

                        posts = posts_data.get('data', [])
                        
                        if not posts:
                            st.info("近期尚無貼文紀錄。")
                        else:
                            parsed_posts = []
                            total_engagement = 0
                            
                            for p in posts:
                                try:
                                    c_time = datetime.strptime(p['created_time'], '%Y-%m-%dT%H:%M:%S%z').astimezone(tw_tz)
                                    likes = p.get('likes', {}).get('summary', {}).get('total_count', 0) if has_engagement_permission else 0
                                    comments = p.get('comments', {}).get('summary', {}).get('total_count', 0) if has_engagement_permission else 0
                                    engagement = likes + comments
                                    total_engagement += engagement
                                    
                                    parsed_posts.append({
                                        'id': p.get('id'), 'time': c_time, 'message': p.get('message', '無文字內容'),
                                        'url': p.get('permalink_url', '#'), 'engagement': engagement, 'likes': likes, 'comments': comments
                                    })
                                except Exception: continue
                            
                            if has_engagement_permission and parsed_posts:
                                avg_eng = total_engagement / len(parsed_posts)
                                top_post = max(parsed_posts, key=lambda x: x['engagement'])
                                
                                if top_post['engagement'] > 0 and top_post['engagement'] >= avg_eng * 1.5:
                                    st.error(f"🔥 **【廣告司令部警告】發現高潛力爆款！**(互動總數: {top_post['engagement']})")
                                    st.info(f"這篇貼文的互動率遠高於您的平均值 ({avg_eng:.1f})，強烈建議「打鐵趁熱」投放廣告來獲取精準客源！")
                                    
                                    with st.expander("🤖 AI 專屬廣告投放策略建議 (點擊展開)", expanded=True):
                                        with st.spinner("正在為您分析這篇貼文的最佳受眾..."):
                                            ad_advice = AISmartHelper.generate_ad_advice(top_post['message'])
                                            st.markdown(ad_advice)
                                            
                                        st.markdown("---")
                                        fb_ad_url = f"https://business.facebook.com/latest/posts/published_posts?asset_id={FB_PAGE_ID}"
                                        st.markdown(f"🚀 [**點我直接前往 Meta 後台，對這篇文章下廣告！**]({fb_ad_url})")

                            st.subheader("📝 近期發文軌跡 (最新 15 篇)")
                            for p in parsed_posts:
                                msg_preview = p['message'][:80].replace('\n', ' ') + "..."
                                with st.container():
                                    if has_engagement_permission:
                                        col_time, col_msg, col_eng, col_link = st.columns([2, 4, 1.5, 1])
                                        with col_time: st.markdown(f"**🗓️ {p['time'].strftime('%Y-%m-%d %H:%M')}**")
                                        with col_msg: st.text(msg_preview)
                                        with col_eng: st.markdown(f"👍 {p['likes']} | 💬 {p['comments']}")
                                        with col_link: st.markdown(f"[🔗 看貼文]({p['url']})")
                                    else:
                                        col_time, col_msg, col_link = st.columns([2, 5, 1])
                                        with col_time: st.markdown(f"**🗓️ {p['time'].strftime('%Y-%m-%d %H:%M')}**")
                                        with col_msg: st.text(msg_preview)
                                        with col_link: st.markdown(f"[🔗 看貼文]({p['url']})")
                                    st.divider()
                                    
                except Exception as e:
                    st.error(f"系統發生預期外的錯誤：{e}")

# ==========================================
# 7. Tab 3: 預定排程管理
# ==========================================
with tab3:
    st.header("🗓️ 排程貼文管理")
    st.markdown("查看並管理目前已經排程、尚未發佈的 Facebook 貼文。")
    
    if st.button("🔄 重新讀取排程清單"):
        st.rerun()
        
    if not FB_PAGE_ID or not FB_TOKEN:
        st.error("⚠️ 缺少 FB_PAGE_ID 或 FB_TOKEN 設定。")
    else:
        with st.spinner("正在向 Facebook 讀取您的排程資料..."):
            try:
                res = requests.get(f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}/scheduled_posts", params={'fields': 'id,message,scheduled_publish_time', 'access_token': FB_TOKEN}).json()
                if 'error' in res:
                    st.error(f"❌ 讀取失敗：{res['error']['message']}")
                else:
                    scheduled_posts = res.get('data', [])
                    if not scheduled_posts:
                        st.info("✅ 目前沒有任何等待發佈的排程貼文。")
                    else:
                        st.success(f"目前共有 **{len(scheduled_posts)}** 篇排程貼文準備發佈：")
                        for p in scheduled_posts:
                            p_id, msg = p['id'], p.get('message', '無文字內容')
                            s_time_val = p.get('scheduled_publish_time')
                            try:
                                if isinstance(s_time_val, int): s_time = datetime.fromtimestamp(s_time_val, tw_tz).strftime('%Y-%m-%d %H:%M')
                                else: s_time = datetime.strptime(s_time_val, '%Y-%m-%dT%H:%M:%S%z').astimezone(tw_tz).strftime('%Y-%m-%d %H:%M')
                            except: s_time = str(s_time_val)
                            
                            with st.expander(f"⏰ 預計發佈時間：{s_time}"):
                                new_msg = st.text_area("修改貼文內容", value=msg, height=200, key=f"edit_{p_id}")
                                col_btn1, col_btn2 = st.columns(2)
                                with col_btn1:
                                    if st.button("💾 儲存修改的文案", key=f"save_{p_id}", use_container_width=True):
                                        if update_fb_post(p_id, new_msg).status_code == 200:
                                            st.success("✅ 修改成功！"); time.sleep(1); st.rerun()
                                        else: st.error("❌ 修改失敗")
                                with col_btn2:
                                    if st.button("🗑️ 取消並刪除此排程", key=f"del_{p_id}", type="primary", use_container_width=True):
                                        if delete_fb_post(p_id).status_code == 200:
                                            st.success("✅ 刪除成功！"); time.sleep(1); st.rerun()
                                        else: st.error("❌ 刪除失敗")
            except Exception as e:
                st.error(f"連線失敗：{e}")
