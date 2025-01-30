import requests
from bs4 import BeautifulSoup
import pymysql
from datetime import datetime, timedelta

# 数据库连接配置
db_config = {
    'host': 'localhost',
    'user': 'root',  # 替换为你的数据库用户名
    'password': '1234',  # 替换为你的数据库密码
    'database': 'spotify_data'
}

# 目标网页 URL
url = "https://kworb.net/spotify/artist/74KM79TiuVKeVCqs8QtB0B_songs.html"

# 发送请求，强制 UTF-8 编码
headers = {"User-Agent": "Mozilla/5.0"}
response = requests.get(url, headers=headers)
response.encoding = "utf-8"  # 关键修复
html = response.text

# 解析网页
soup = BeautifulSoup(html, "html.parser")

# 找到所有表格行（tr）
rows = soup.find_all("tr")

# 存储数据
song_data = []

# 跳过前三行，从第四行开始处理
for row in rows[4:]:  # 修改这里，添加切片 [3:]
    cols = row.find_all("td")
    if len(cols) >= 4:
        # 处理歌曲名：替换符号 + 统一小写 + 去除空格
        song_name = (
            cols[0].text.strip()
            .replace("'", "'")
            .replace("'", "'")
            .replace("＆", "&")
            .replace(""", '"')
            .replace(""", '"')
            .strip()
            .lower()
        )

        # 处理播放量
        total_streams = cols[1].text.strip().replace(",", "")
        daily_streams = cols[2].text.strip().replace(",", "")

        song_data.append({
            "歌曲名": song_name,
            "总播放量": int(total_streams) if total_streams.isdigit() else 0,
            "每日播放量": int(daily_streams) if daily_streams.isdigit() else 0
        })

# 修改日期计算逻辑
today = datetime.now()
current_date = (today - timedelta(days=2)).strftime("%Y-%m-%d")  # 获取前天的数据

try:
    # 建立数据库连接
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    # 创建表（如果不存在）- 确保日期和歌曲名是联合主键
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS SabrinaDaliyData (
        日期 DATE,
        歌曲名 VARCHAR(255),
        总播放量 BIGINT,
        每日播放量 BIGINT,
        PRIMARY KEY (日期, 歌曲名)  # 确保这里有联合主键
    )
    """
    cursor.execute(create_table_sql)

    # 插入或更新数据
    for data in song_data:
        sql = """
        INSERT INTO SabrinaDaliyData (日期, 歌曲名, 总播放量, 每日播放量)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            总播放量 = VALUES(总播放量),
            每日播放量 = VALUES(每日播放量)
        """
        cursor.execute(sql, (
            current_date,
            data['歌曲名'],
            data['总播放量'],
            data['每日播放量']
        ))

    # 提交更改
    conn.commit()
    print(f"数据已成功保存/更新到数据库，日期：{current_date}")

except pymysql.Error as err:
    print(f"数据库错误: {err}")
    if 'conn' in locals():
        conn.rollback()

finally:
    if 'conn' in locals():
        cursor.close()
        conn.close()
        print("数据库连接已关闭")