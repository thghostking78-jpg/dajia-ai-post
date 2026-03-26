import os
import requests
import pandas as pd

# 從環境變數讀取金鑰 (若在本地端測試，可直接替換成您的字串)
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_TOKEN = os.environ.get("FB_TOKEN")

def fetch_fb_performance():
    print("🔍 開始抓取有巢氏大甲店粉專成效資料...")
    
    # 使用 Graph API 抓取已發佈的貼文，以及它們的按讚數、留言數與分享數
    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/published_posts"
    params = {
        'fields': 'id,message,created_time,likes.summary(true),comments.summary(true),shares',
        'access_token': FB_TOKEN,
        'limit': 10  # 先抓取最近 10 篇貼文來分析
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code != 200:
        print("❌ 抓取失敗：", response.text)
        return
        
    data = response.json().get('data', [])
    
    # 整理成方便閱讀的列表
    report_data = []
    for post in data:
        # 擷取貼文前 20 個字當作摘要，方便辨識是哪個物件
        msg_preview = post.get('message', '無文字內容')[:20].replace('\n', ' ') + "..."
        
        # 取得互動數據
        likes = post.get('likes', {}).get('summary', {}).get('total_count', 0)
        comments = post.get('comments', {}).get('summary', {}).get('total_count', 0)
        shares = post.get('shares', {}).get('count', 0)
        
        report_data.append({
            "📅 發文時間": post.get('created_time')[:10],
            "📝 貼文摘要": msg_preview,
            "👍 按讚數": likes,
            "💬 留言數": comments,
            "🔄 分享數": shares
        })
        
    # 使用 Pandas 轉換成表格並印出
    if report_data:
        df = pd.DataFrame(report_data)
        print("\n📊 === 本週大甲房產行銷成效報表 ===")
        print(df.to_string(index=False))
        print("=====================================\n")
    else:
        print("目前粉專上還沒有發佈過貼文喔！")

if __name__ == "__main__":
    fetch_fb_performance()
