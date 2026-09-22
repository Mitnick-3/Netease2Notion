import os
import sys
import json
import requests

# 环境变量获取
NCM_COOKIE = os.getenv("NCM_COOKIE")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
NCM_USER_ID = os.getenv("NCM_USER_ID")

if not all([NCM_COOKIE, NOTION_TOKEN, NOTION_DATABASE_ID, NCM_USER_ID]):
    print("错误: 缺少必要的环境变量配置！")
    sys.exit(1)

# Notion API Headers
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# 1. 获取网易云播放记录 (周听歌榜/历史听歌榜，type=1 周榜, type=0 所有时间)
def get_ncm_record(user_id, cookie_str):
    url = f"https://music.163.com/api/v1/play/record?uid={user_id}&type=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Cookie": cookie_str,
        "Referer": "https://music.163.com/"
    }
    resp = requests.get(url, headers=headers)
    data = resp.json()
    if data.get("code") != 200:
        print(f"获取网易云数据失败: {data}")
        return []
    
    week_data = data.get("weekData", [])
    songs = []
    for item in week_data:
        song_info = item.get("song", {})
        songs.append({
            "id": str(song_info.get("id")),
            "name": song_info.get("name"),
            "artist": "/".join([a.get("name") for a in song_info.get("ar", [])]),
            "album": song_info.get("al", {}).get("name"),
            "cover": song_info.get("al", {}).get("picUrl"),
            "play_count": item.get("playCount"),
            "url": f"https://music.163.com/#/song?id={song_info.get('id')}"
        })
    return songs

# 2. 查询 Notion 中已存在的记录 (避免重复插入，采用 Update)
def query_notion_existing(song_id):
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    payload = {
        "filter": {
            "property": "MusicID",
            "rich_text": {
                "equals": song_id
            }
        }
    }
    resp = requests.post(url, headers=NOTION_HEADERS, json=payload)
    if resp.status_code == 200:
        results = resp.json().get("results", [])
        if results:
            return results[0]["id"]
    return None

# 3. 写入或更新 Notion
def sync_to_notion(song):
    page_id = query_notion_existing(song["id"])
    
    # 确保 URL 是标准的 https 开头
    cover_url = song.get("cover", "")
    if cover_url and cover_url.startswith("http://"):
        cover_url = cover_url.replace("http://", "https://")

    properties = {
        "Song": {"title": [{"text": {"content": song["name"] or "未知歌名"}}]},
        "Artist": {"rich_text": [{"text": {"content": song["artist"] or "未知歌手"}}]},
        "Album": {"rich_text": [{"text": {"content": song["album"] or "未知专辑"}}]},
        "PlayCount": {"number": int(song["play_count"] or 0)},
        "MusicID": {"rich_text": [{"text": {"content": str(song["id"])}}]},
        "Url": {"url": song["url"]}
    }
    
    # 仅当封面 URL 有效且为 https 时才添加 Cover 字段
    if cover_url and cover_url.startswith("https://"):
        properties["Cover"] = {
            "files": [{
                "name": f"cover_{song['id']}.jpg",
                "type": "external",
                "external": {"url": cover_url}
            }]
        }

    if page_id:
        url = f"https://api.notion.com/v1/pages/{page_id}"
        resp = requests.patch(url, headers=NOTION_HEADERS, json={"properties": properties})
    else:
        url = "https://api.notion.com/v1/pages"
        payload = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": properties
        }
        resp = requests.post(url, headers=NOTION_HEADERS, json=payload)
    
    if resp.status_code == 200:
        print(f"同步成功: {song['name']}")
    else:
        # 打印详细的 Notion 报错 JSON 内容，方便定位
        print(f"同步失败: {song['name']} -> HTTP {resp.status_code}")
        print(f"报错详情: {resp.text}")

def main():
    songs = get_ncm_record(NCM_USER_ID, NCM_COOKIE)
    print(f"共获取到 {len(songs)} 条记录，开始同步到 Notion...")
    for song in songs:
        sync_to_notion(song)

if __name__ == "__main__":
    main()
