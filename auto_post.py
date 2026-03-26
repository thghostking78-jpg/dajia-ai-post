import os
import requests
import random
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ==========================================
# 1. 讀取 GitHub Secrets 環境變數
# ==========================================
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_TOKEN = os.environ.get("FB_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")

if not GEMINI_KEY or not FB_TOKEN:
    print("❌ 錯誤：找不到 API 密鑰，請檢查 GitHub Secrets 設定！")
    exit(1)

genai.configure(api_key=GEMINI_KEY)
ai_model = genai.GenerativeModel('gemini-2.5-flash')

# ==========================================
# 2. 建立你的「大甲好屋資料庫」(可隨時擴充)
# ==========================================
# 每天程式執行時，會從這裡「隨機」挑選一筆發文，避免重複！
properties_db = [
    {
        "物件名稱": "大甲鎮瀾商圈黃金透天",
        "總價": "1580萬",
        "建坪": "55坪",
        "地坪": "25坪",
        "格局": "5房2廳3衛",
        "特色": "近車站、生活機能極佳、屋況免整理"
    },
    {
        "物件名稱": "大甲體育場旁採光美墅",
        "總價": "1280萬",
        "建坪": "48坪",
        "地坪": "28坪",
        "格局": "4房2廳3衛",
        "特色": "邊間採光佳、近學區、自有車庫好停車"
    },
    {
        "物件名稱": "孔子廟文教區質感電梯大樓",
        "總價": "898萬",
        "建坪": "35坪",
        "地坪": "持分",
        "格局": "3房2廳2衛",
        "特色": "高樓層景觀戶、24小時保安管理、雙語學區"
    }
]

# ==========================================
# 3. 核心發文邏輯
# ==========================================
def generate_and_post():
    print("🚀 啟動有巢氏大甲店每日自動發文程序...")
    
    # 隨機挑選一個物件與一種行銷風格
    selected_property = random.choice(properties_db)
    styles = ["在地專業", "溫馨感性", "限時急售", "精簡快訊"]
    selected_style = random.choice(styles)
    
    print(f"🏠 本日選定物件：{selected_property['物件名稱']}")
    print(f"🎨 本日 AI 文案風格：{selected_style}")
    
    # 整理物件資訊
    details = "\n".join([f"{k}：{v}" for k, v in selected_property.items()])
    
    style_prompts = {
        "在地專業": "強調大甲在地地段潛力、投資報酬率與專業行情分析。",
        "溫馨感性": "強調成家夢想、空間給予家人的溫度、大甲生活圈的便利與人情味。",
        "限時急售": "營造物件稀有性、超值價格、手刀預約的急迫感。",
        "精簡快訊": "極簡風格，只列出標題、總價、坪數與一句最有力的特色，適合快速滑過的讀者。"
    }
    
    # 整合我們剛剛優化過的 Prompt 提示詞
    prompt = f"""
    你是一位台中大甲區的房仲行銷專家，目前在『有巢氏房屋大甲加盟店』服務。
    請根據以下物件資訊撰寫一份精簡、吸睛的 FB 貼文。
    
    【文案風格】: {style_prompts.get(selected_style)}
    【物件資訊】:
    {details}
    
    【精簡化要求】:
    1. 標題必須包含物件名稱與總價，確保客人在沒點開「查看更多」前就能看到核心價值。
    2. 特色：精選幾個最重要的優點，用短句條列。
    3. 規格：只保留總價、地坪(若有)、格局，並排顯示以節省空間。
    4. 若選「精簡快訊」，總字數嚴格控制在 100 字內，用 3 個 Bullet points 結案。

    【格式要求】:
    - 標題要吸睛，適當使用 Emoji。
    - 結尾固定附上：
      🏠 **有巢氏房屋大甲店 (孔子廟對面)**
      📞 **賞屋專線：04-26888050**
      📍 **大甲區文武路99號**
    - 標籤：#大甲房產 #大甲買屋 #有巢氏房屋
    
    請直接給出文案內容，不要有任何前言或碎念。
    """
    
    # 放寬 AI 審查機制，避免正常的房地產廣告詞被攔截
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
    
    try:
        print("🤖 正在呼叫 Gemini 生成專業文案...")
        copy_text = ai_model.generate_content(prompt, safety_settings=safety_settings).text
        print("✅ 文案生成完畢！")
        print("-" * 30)
        print(copy_text)
        print("-" * 30)
    except Exception as e:
        print(f"❌ AI 生成失敗：{e}")
        return

    # 4. 發佈到 Facebook 粉絲專頁
    print("📡 正在同步至 Facebook...")
    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
    payload = {
        'message': copy_text,
        'access_token': FB_TOKEN
    }
    
    res = requests.post(url, data=payload)
    if res.status_code == 200:
        print(f"🎉 發佈成功！貼文ID: {res.json().get('id')}")
    else:
        print(f"❌ 發佈失敗：{res.text}")

if __name__ == "__main__":
    generate_and_post()
