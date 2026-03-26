import os
import requests
import pytz
from datetime import datetime
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# 1. 從 GitHub Secrets 讀取環境變數 (不再使用 st.secrets)
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_TOKEN = os.environ.get("FB_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")

genai.configure(api_key=GEMINI_KEY)
ai_model = genai.GenerativeModel('gemini-2.5-flash')

def generate_and_post():
    print("啟動大甲有巢氏自動發文程序...")
    
    # 2. 這裡可以改為從 CSV、Google Sheets 或直接寫死的當週主打物件
    data_payload = {
        "物件名稱": "大甲鎮瀾商圈黃金透天",
        "總價": "1580萬",
        "建坪": "55坪",
        "格局": "5房2廳3衛",
        "特色": "近車站、生活機能極佳、屋況免整理"
    }
    
    details = "\n".join([f"{k}：{v}" for k, v in data_payload.items()])
    prompt = f"""
    你是一位台中大甲區的房仲行銷專家。請根據以下物件資訊撰寫FB貼文。
    【文案風格】: 在地專業
    【物件資訊】:\n{details}
    結尾附上：
    🏠 有巢氏房屋大甲加盟店
    📞 服務專線：04-26888050
    """
    
    # 3. AI 生成文案
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    }
    copy_text = ai_model.generate_content(prompt, safety_settings=safety_settings).text
    print("文案生成完畢！")

    # 4. 發佈到 Facebook (此處以純文字發佈為例，若需照片可結合您原本的圖檔邏輯)
    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
    payload = {
        'message': copy_text,
        'access_token': FB_TOKEN
    }
    
    res = requests.post(url, data=payload)
    if res.status_code == 200:
        print(f"✅ 發佈成功！貼文ID: {res.json().get('id')}")
    else:
        print(f"❌ 發佈失敗：{res.text}")

if __name__ == "__main__":
    generate_and_post()
