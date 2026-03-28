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
        st.warning("🔒 有巢氏大甲店內部專用系統")
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
        link_text = f"👉 **詳細資訊請看：**\n{data_dict.get('專屬網址')}\n" if data_dict.get('專屬網址') else ""
        
        # 根據發文類型選擇 Prompt
        if post_type == "🏠 專業售屋":
            style_prompts = {
                "在地專業": "語氣穩重專業，客觀分析地段潛力與市場行情。",
                "溫馨感性": "語氣溫暖，點出空間給家人的實用性與成家願景。",
                "限時急售": "節奏快、強調單價優勢與稀有度，創造急迫感。",
                "精簡快訊": "極簡風格，不廢話，條列核心賣點。",
                "空拍視野": "大氣開闊，描述地形、聯外道路與無敵視野。"
            }
            prompt = f"""
            你是一位台中大甲區的頂尖房仲。請根據以下資訊寫 FB 貼文。
            【風格】: {style_prompts.get(style)}
            【資訊】:\n{details}
            請包含吸睛標題、重點條列、視覺亮點分析，並在結尾放上：
            ---
            {link_text}🏠 **有巢氏房屋台中大甲店**
            📞 **賞屋專線：04-26888050**
            """
            
        elif post_type == "🍜 在地生活圈":
            prompt = f"""
            你是一位台中大甲區在地房仲。請寫一篇接地氣的在地生活 FB 貼文。
            【主題】：{data_dict.get('主題/地點')}
            【心得】：{data_dict.get('關鍵字')}
            語氣要像在地人推薦朋友，自然熱情，結尾自然帶出房仲身分（例如吃飽繼續去帶看）。
            結尾放上：
            ---
            🏠 **有巢氏房屋台中大甲店**
            📞 **專線：04-26888050**
            """
            
        elif post_type == "🎬 萌娃主播腳本":
            prompt = f"""
            你是一位專門撰寫短影音腳本的企劃。
            請根據以下物件資訊，寫一份約 30~40 秒的 Reels 短影音腳本。
            
            【特別設定】：
            這支影片的講解者是房仲的超萌寶貝（妡妡 或 沐沐）。
            台詞必須充滿「童言童語的可愛感」，但又要能精準幫爸爸講出房子最吸引大人的賣點（如大空間、停車、好學區等）。
            
            【物件資訊】:
            {details}
            
            【腳本結構】：
            1. [畫面指示]：標示現在畫面應該放什麼照片或字卡。
            2. [萌娃台詞]：直接寫出要讓 AI 數位人唸的台詞。例如：「各位叔叔阿姨好！我是沐沐！我爸爸今天說大甲有一間超大的房子...」
            3. [結尾行動]：用可愛的方式叫大家趕快打電話給爸爸買房子。
            
            請以表格或分段的形式，清晰輸出畫面與台詞的搭配。
            """

        models_to_try = [
            "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"
        ]
        
        for model_name in models_to_try:
            try:
                return get_cached_ai_response(prompt, model_name, image_bytes)
            except Exception as e:
                time.sleep(2)
                continue
        return "❌ 生成失敗，請稍後再試。"

    @staticmethod
    def add_watermark(image_bytes, text="有巢氏台中大甲店", position_type="右下角", color_theme="專屬綠 (推薦)"):
        # (浮水印邏輯保持不變)
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
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
            margin = int(w * 0.03)
            
            if position_type == "左下角": position = (margin, h - th - margin)
            elif position_type == "置中": position = ((w - tw) // 2, (h - th) // 2)
            else: position = (w - tw - margin, h - th - margin)
            
            if color_theme == "專屬綠 (推薦)":
                main_color, stroke_color = (0, 153, 76, 240), (255, 255, 255, 255) 
            elif color_theme == "亮眼黃":
                main_color, stroke_color = (255, 215, 0, 240), (30, 30, 30, 255)    
            else: 
                main_color, stroke_color = (255, 255, 255, 240), (30, 30, 30, 255)    

            draw.text((position[0]+3, position[1]+3), text, font=font, fill=(0, 0, 0, 150))
            draw.text(position, text, font=font, fill=main_color, stroke_width=3, stroke_fill=stroke_color)
            return Image.alpha_composite(img, txt_layer).convert("RGB")
        except: return None

# ==========================================
# 4. FB API 溝通層
# ==========================================
def upload_photo_to_fb(image_obj):
    buf = io.BytesIO()
    image_obj.save(buf, format='JPEG', quality=90)
    buf.seek(0)
    res = requests.post(f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}/photos", data={'published': 'false', 'access_token': FB_TOKEN}, files={'source': buf})
    return res.json().get('id'), res.json().get('error')

def post_to_feed(message, photo_ids, scheduled_time=None):
    payload = {'message': message, 'access_token': FB_TOKEN}
    if scheduled_time:
        payload.update({'published': 'false', 'scheduled_publish_time': scheduled_time})
    for i, p_id in enumerate(photo_ids):
        payload[f'attached_media[{i}]'] = f'{{"media_fbid": "{p_id}"}}'
    return requests.post(f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}/feed", data=payload)

def delete_fb_post(post_id):
    return requests.delete(f"https://graph.facebook.com/v25.0/{post_id}", params={'access_token': FB_TOKEN})

def update_fb_post(post_id, new_message):
    return requests.post(f"https://graph.facebook.com/v25.0/{post_id}", data={'message': new_message, 'access_token': FB_TOKEN})

def reset_app_state():
    st.session_state['generated_posts'], st.session_state['ordered_images'] = [], []
    st.rerun()

# ==========================================
# 5. 主介面 UI
# ==========================================
st.title("🚀 發文小幫手 Master Pro")
check_fb_token_health() 

for key in ['generated_posts', 'ordered_images', 'last_uploaded_names']:
    if key not in st.session_state: st.session_state[key] = []
if 'watermark_pos' not in st.session_state: st.session_state['watermark_pos'] = "右下角"
if 'watermark_color' not in st.session_state: st.session_state['watermark_color'] = "專屬綠 (推薦)"

tab1, tab2, tab3 = st.tabs(["🚀 AI 自動發文與排程", "📊 粉專成效儀表板", "🗓️ 預定排程管理"])

with tab1:
    post_type = st.radio("📝 選擇模式", ["🏠 專業售屋", "🍜 在地生活圈", "🎬 萌娃主播腳本"], horizontal=True)
    st.markdown("---")
    
    m_col1, m_col2, m_col3 = st.columns(3)
    
    if post_type in ["🏠 專業售屋", "🎬 萌娃主播腳本"]:
        with m_col1:
            name = st.text_input("🏠 物件名稱*", placeholder="大甲鎮瀾商圈美墅")
            address = st.text_input("📍 物件地址", placeholder="大甲區中山路一段")
            price = st.number_input("💰 總價 (萬)", 0, step=10, value=1200)
            ping = st.number_input("📐 建坪 (坪)", 0.0, step=0.1, value=45.0)
            land_ping = st.number_input("🌲 地坪 (坪)", 0.0, step=0.1, value=25.0)
        with m_col2:
            floor = st.text_input("🏢 樓層", placeholder="3樓 / 總10樓")
            layout = st.text_input("🚪 格局", placeholder="4房2廳3衛")
            parking = st.selectbox("🚗 車位", ["無", "自有車庫", "坡道平面", "門口停車"])
            link = st.text_input("🔗 物件專屬網址")
            features = st.text_area("✨ 物件特色", placeholder="近學區、採光好...")
            uploaded_files = st.file_uploader("📸 照片上傳", type=['jpg','png'], accept_multiple_files=True)
    else:
        with m_col1:
            life_title = st.text_input("📍 主題*", placeholder="鎮瀾宮粉腸")
            life_keywords = st.text_area("✨ 心得", placeholder="從小吃到大...")
        with m_col2:
            uploaded_files = st.file_uploader("上傳生活圈照片", type=['jpg','png'], accept_multiple_files=True)
            
    with m_col3:
        if post_type == "🏠 專業售屋":
            selected_styles = st.multiselect("🎨 風格", ["在地專業", "溫馨感性", "限時急售", "精簡快訊", "空拍視野"], default=["精簡快訊"])
        else:
            selected_styles = ["專屬腳本生成" if post_type == "🎬 萌娃主播腳本" else "在地生活"]
            st.info(f"🎨 當前模式：{selected_styles[0]}")
        
        mode = st.radio("發佈模式", ["⚡ 立即發佈", "📅 自訂多天排程"], horizontal=True)
        time_options = [f"{h:02d}:{m:02d}" for h in range(7, 22) for m in (0, 30) if not (h==21 and m==30)]
        post_schedules = []
        
        if mode == "📅 自訂多天排程":
            num_posts = st.slider("📌 幾篇？", 1, 10, 1)
            for i in range(num_posts):
                col_d, col_t = st.columns(2)
                with col_d: d = st.date_input(f"第 {i+1} 篇", datetime.now(tw_tz).date() + timedelta(days=i*2), key=f"d_{i}")
                with col_t: t_str = st.selectbox(f"時間", time_options, key=f"t_{i}")
                post_schedules.append(tw_tz.localize(datetime.combine(d, datetime.strptime(t_str, "%H:%M").time())))
        else:
            post_schedules.append(datetime.now(tw_tz) + timedelta(minutes=15))

    if uploaded_files:
        if st.session_state['last_uploaded_names'] != [f.name for f in uploaded_files]:
            st.session_state['ordered_images'] = [f.getvalue() for f in uploaded_files]
            st.session_state['last_uploaded_names'] = [f.name for f in uploaded_files]

        st.subheader("🖼️ 浮水印設定")
        col_pos, col_color = st.columns(2)
        with col_pos: watermark_pos = st.radio("位置", ["右下角", "左下角", "置中"], horizontal=True, index=["右下角", "左下角", "置中"].index(st.session_state['watermark_pos']))
        with col_color: watermark_color = st.radio("顏色", ["經典白", "專屬綠 (推薦)", "亮眼黃"], horizontal=True, index=["經典白", "專屬綠 (推薦)", "亮眼黃"].index(st.session_state['watermark_color']))
        st.session_state['watermark_pos'], st.session_state['watermark_color'] = watermark_pos, watermark_color
        
        if st.session_state['ordered_images']:
            cols = st.columns(len(st.session_state['ordered_images']))
            for idx, img_bytes in enumerate(st.session_state['ordered_images']):
                preview_img = AISmartHelper.add_watermark(img_bytes, watermark_pos, watermark_color)
                with cols[idx]:
                    if preview_img: st.image(preview_img, use_container_width=True)
                    btn1, btn2 = st.columns(2)
                    with btn1:
                        if idx > 0 and st.button("⬅️", key=f"l_{idx}"):
                            st.session_state['ordered_images'][idx], st.session_state['ordered_images'][idx-1] = st.session_state['ordered_images'][idx-1], st.session_state['ordered_images'][idx]
                            st.rerun()
                    with btn2:
                        if idx < len(st.session_state['ordered_images'])-1 and st.button("➡️", key=f"r_{idx}"):
                            st.session_state['ordered_images'][idx], st.session_state['ordered_images'][idx+1] = st.session_state['ordered_images'][idx+1], st.session_state['ordered_images'][idx]
                            st.rerun()

    st.markdown("---")
    if st.button("🤖 啟動 AI 生成", type="primary", use_container_width=True):
        if post_type in ["🏠 專業售屋", "🎬 萌娃主播腳本"] and not name: st.error("請填物件名稱"); st.stop()
        elif post_type == "🍜 在地生活圈" and not life_title: st.error("請填主題"); st.stop()
            
        data_payload = {"物件名稱": name, "地址": address, "總價": f"{price}萬", "建坪": f"{ping}坪", "地坪": f"{land_ping}坪", "樓層": floor, "格局": layout, "車位": parking, "專屬網址": link, "特色": features} if post_type != "🍜 在地生活圈" else {"主題/地點": life_title, "關鍵字": life_keywords}
            
        st.session_state['generated_posts'] = []
        progress_text = st.empty()
        
        for i, target_dt in enumerate(post_schedules):
            target_dt = max(target_dt, datetime.now(tw_tz) + timedelta(minutes=15))
            current_style = selected_styles[i % len(selected_styles)]
            progress_text.info(f"⏳ 生成中 ({current_style})...")
            img_b = st.session_state['ordered_images'][0] if st.session_state['ordered_images'] else None
            
            st.session_state['generated_posts'].append({
                "發文時間": target_dt, "風格": current_style,
                "文案": AISmartHelper.generate_copy(data_payload, current_style, img_b, post_type)
            })
        progress_text.success("✅ AI 生成完畢！")

    if st.session_state['generated_posts']:
        for idx, post in enumerate(st.session_state['generated_posts']):
            with st.expander(f"預計發佈：{post['發文時間'].strftime('%Y-%m-%d %H:%M')} ({post['風格']})", expanded=True):
                st.session_state['generated_posts'][idx]['文案'] = st.text_area("內容", value=post['文案'], height=250, key=f"t_{idx}")

        col1, col2 = st.columns([3, 1])
        with col1:
            if st.button("🚀 排程至 Facebook", type="primary", use_container_width=True):
                if post_type != "🎬 萌娃主播腳本" and not st.session_state['ordered_images']:
                    st.error("需照片！")
                else:
                    with st.status("上傳中..."):
                        p_ids = []
                        for file_b in st.session_state['ordered_images']:
                            pid, _ = upload_photo_to_fb(AISmartHelper.add_watermark(file_b, st.session_state['watermark_pos'], st.session_state['watermark_color']))
                            if pid: p_ids.append(pid)
                        
                        success = 0
                        for post in st.session_state['generated_posts']:
                            ts = int(post['發文時間'].timestamp()) if mode != "⚡ 立即發佈" else None
                            if ts and ts < int(datetime.now().timestamp()) + 600: ts = int(datetime.now().timestamp()) + 900
                            if post_to_feed(post['文案'], p_ids, ts).status_code == 200: success += 1
                        
                        if success == len(st.session_state['generated_posts']):
                            st.success(f"🎉 成功！({success}篇)")
                            st.session_state['post_success'] = True
        with col2:
            if st.session_state.get('post_success'):
                if st.button("✨ 完成", use_container_width=True): reset_app_state()

# ==========================================
# Tab 2 & 3 保持不變 (粉專儀表板與排程管理)
# ==========================================
# (此處為了代碼長度省略，這兩個 Tab 完全套用上一版本的邏輯即可)

# ==========================================
# 6. Tab 2: 粉專成效儀表板
# ==========================================
with tab2:
    st.header("📈 粉絲專頁營運戰情室")
    st.markdown("追蹤您的粉專成長軌跡與近期發文紀錄。")
    
    if st.button("🔄 撈取最新營運數據"):
        if not FB_PAGE_ID or not FB_TOKEN:
            st.error("⚠️ 缺少 FB_PAGE_ID 或 FB_TOKEN 設定。")
        else:
            with st.spinner("正在與 Facebook 連線，解析近期營運數據中..."):
                api_base = f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}"
                
                try:
                    page_params = {'fields': 'fan_count,followers_count,name', 'access_token': FB_TOKEN}
                    page_data = requests.get(api_base, params=page_params).json()
                    
                    if 'error' in page_data:
                        st.error(f"❌ 無法撈取粉專資料：{page_data['error']['message']}")
                    else:
                        page_name = page_data.get('name', '有巢氏台中大甲店')
                        fan_count = page_data.get('fan_count', 0)
                        followers_count = page_data.get('followers_count', 0)
                        
                        st.success(f"✅ 成功連線至粉專：**{page_name}**")
                        
                        met_col1, met_col2 = st.columns(2)
                        met_col1.metric("👥 總粉絲專頁讚數", f"{int(fan_count):,}")
                        met_col2.metric("🔔 總追蹤人數", f"{int(followers_count):,}")
                        
                        st.markdown("---")
                        
                        posts_url = f"{api_base}/published_posts"
                        advanced_params = {
                            'fields': 'created_time,message,permalink_url,likes.summary(true),comments.summary(true)',
                            'limit': 15,
                            'access_token': FB_TOKEN
                        }
                        
                        posts_res = requests.get(posts_url, params=advanced_params)
                        posts_data = posts_res.json()
                        
                        has_engagement_permission = True
                        if 'error' in posts_data:
                            err_code = posts_data['error'].get('code')
                            if err_code in [10, 100]:
                                has_engagement_permission = False
                                fb_real_msg = posts_data['error'].get('message', '無詳細說明')
                                st.warning(f"⚠️ 目前的 FB Token 缺少讀取按讚與留言的權限 (pages_read_engagement)，已自動切換為「基本顯示模式」。\nFB 回傳錯誤: {fb_real_msg}")
                                
                                basic_params = {
                                    'fields': 'created_time,message,permalink_url',
                                    'limit': 15,
                                    'access_token': FB_TOKEN
                                }
                                posts_res = requests.get(posts_url, params=basic_params)
                                posts_data = posts_res.json()
                            else:
                                st.error(f"❌ 獲取貼文失敗：{posts_data['error']['message']}")
                                posts_data = {'data': []}

                        posts = posts_data.get('data', [])
                        
                        if not posts:
                            st.info("近期尚無貼文紀錄。")
                        else:
                            parsed_posts = []
                            seven_days_ago = datetime.now(tw_tz) - timedelta(days=7)
                            top_post = None
                            max_engagement = -1
                            
                            for p in posts:
                                try:
                                    c_time = datetime.strptime(p['created_time'], '%Y-%m-%dT%H:%M:%S%z').astimezone(tw_tz)
                                    msg = p.get('message', '無文字內容 (可能僅有照片或影片)')
                                    url = p.get('permalink_url', '#')
                                    
                                    likes = p.get('likes', {}).get('summary', {}).get('total_count', 0) if has_engagement_permission else 0
                                    comments = p.get('comments', {}).get('summary', {}).get('total_count', 0) if has_engagement_permission else 0
                                    engagement = likes + comments
                                    
                                    parsed_posts.append({
                                        'time': c_time,
                                        'message': msg,
                                        'url': url,
                                        'engagement': engagement,
                                        'likes': likes,
                                        'comments': comments
                                    })
                                    
                                    if has_engagement_permission and c_time > seven_days_ago and engagement > max_engagement and engagement > 0:
                                        max_engagement = engagement
                                        top_post = parsed_posts[-1]
                                        
                                except Exception:
                                    continue

                            if has_engagement_permission and top_post:
                                st.success(f"🔥 **本週成效冠軍發現！** (互動總數: {top_post['engagement']})")
                                st.info(f"👍 按讚: {top_post['likes']} | 💬 留言: {top_post['comments']}\n\n內文片段：{top_post['message'][:50]}...\n\n[👉 點此查看貼文]({top_post['url']})")
                                st.markdown("---")

                            st.subheader("📝 近期發文軌跡 (最新 15 篇)")
                            for p in parsed_posts:
                                msg_preview = p['message'][:80].replace('\n', ' ') + "..."
                                with st.container():
                                    if has_engagement_permission:
                                        col_time, col_msg, col_eng, col_link = st.columns([2, 4, 1.5, 1])
                                        with col_time: st.markdown(f"**🗓️ {p['time'].strftime('%Y-%m-%d %H:%M')}**")
                                        with col_msg: st.text(msg_preview)
                                        with col_eng: st.markdown(f"👍 {p['likes']} | 💬 {p['comments']}")
                                        with col_link: st.markdown(f"[🔗 看成效]({p['url']})")
                                    else:
                                        col_time, col_msg, col_link = st.columns([2, 5, 1])
                                        with col_time: st.markdown(f"**🗓️ {p['time'].strftime('%Y-%m-%d %H:%M')}**")
                                        with col_msg: st.text(msg_preview)
                                        with col_link: st.markdown(f"[🔗 看成效]({p['url']})")
                                    st.divider()
                                    
                except Exception as e:
                    st.error(f"系統發生預期外的錯誤：{e}")

# ==========================================
# 7. Tab 3: 預定排程管理
# ==========================================
with tab3:
    st.header("🗓️ 排程貼文管理")
    st.markdown("查看並管理目前已經排程、尚未發佈的 Facebook 貼文。（請注意：若需修改照片，建議直接刪除此排程重新發布。）")
    
    if st.button("🔄 重新讀取排程清單"):
        st.rerun()
        
    if not FB_PAGE_ID or not FB_TOKEN:
        st.error("⚠️ 缺少 FB_PAGE_ID 或 FB_TOKEN 設定。")
    else:
        with st.spinner("正在向 Facebook 讀取您的排程資料..."):
            url = f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}/scheduled_posts"
            params = {
                'fields': 'id,message,scheduled_publish_time',
                'access_token': FB_TOKEN
            }
            
            try:
                res = requests.get(url, params=params).json()
                if 'error' in res:
                    st.error(f"❌ 讀取失敗：{res['error']['message']}")
                else:
                    scheduled_posts = res.get('data', [])
                    if not scheduled_posts:
                        st.info("✅ 目前沒有任何等待發佈的排程貼文。")
                    else:
                        st.success(f"目前共有 **{len(scheduled_posts)}** 篇排程貼文準備發佈：")
                        
                        for p in scheduled_posts:
                            p_id = p['id']
                            msg = p.get('message', '無文字內容')
                            
                            s_time_val = p.get('scheduled_publish_time')
                            try:
                                if isinstance(s_time_val, int):
                                    s_time = datetime.fromtimestamp(s_time_val, tw_tz).strftime('%Y-%m-%d %H:%M')
                                else:
                                    s_time = datetime.strptime(s_time_val, '%Y-%m-%dT%H:%M:%S%z').astimezone(tw_tz).strftime('%Y-%m-%d %H:%M')
                            except Exception:
                                s_time = str(s_time_val)
                            
                            with st.expander(f"⏰ 預計發佈時間：{s_time}"):
                                new_msg = st.text_area("修改貼文內容", value=msg, height=200, key=f"edit_{p_id}")
                                
                                col_btn1, col_btn2 = st.columns(2)
                                with col_btn1:
                                    if st.button("💾 儲存修改的文案", key=f"save_{p_id}", use_container_width=True):
                                        update_res = update_fb_post(p_id, new_msg)
                                        if update_res.status_code == 200:
                                            st.success("✅ 修改成功！")
                                            time.sleep(1)
                                            st.rerun()
                                        else:
                                            st.error(f"❌ 修改失敗：{update_res.json()}")
                                            
                                with col_btn2:
                                    if st.button("🗑️ 取消並刪除此排程", key=f"del_{p_id}", type="primary", use_container_width=True):
                                        del_res = delete_fb_post(p_id)
                                        if del_res.status_code == 200:
                                            st.success("✅ 刪除成功！")
                                            time.sleep(1)
                                            st.rerun()
                                        else:
                                            st.error(f"❌ 刪除失敗：{del_res.json()}")
            except Exception as e:
                st.error(f"連線失敗：{e}")
