from datetime import datetime, timedelta
import pymysql
import pandas as pd

# 数据库配置
db_host = "localhost"
db_user = "root"
db_password = "1234"
db_name = "spotify_data"

# 连接数据库
conn = pymysql.connect(
    host=db_host, user=db_user, password=db_password,
    database=db_name, charset="utf8mb4"
)
cursor = conn.cursor()

# 计算日期
today = datetime.now()
current_date = (today - timedelta(days=2)).strftime("%Y-%m-%d")  # 获取前天的数据
previous_date = (today - timedelta(days=3)).strftime("%Y-%m-%d")  # 获取大前天的数据

# 从数据库读取数据替代读取Excel
sql = """
SELECT 歌曲名, 总播放量, 每日播放量
FROM SabrinaDaliyData
WHERE 日期 = %s
"""
cursor.execute(sql, (current_date,))
results = cursor.fetchall()

# 将查询结果转换为DataFrame
df = pd.DataFrame(results, columns=["歌曲名", "总播放量", "每日播放量"])

# 目标歌曲列表（注意使用半角符号）
short_n_sweet_songs = [
    "Taste", "Please Please Please", "Good Graces", "Sharpest Tool",
    "Coincidence", "Bed Chem", "Espresso", "Dumb & Poetic",
    "Slim Pickins", "Juno", "Lie To Girls", "Don't Smile"
]
emails_i_cant_send_songs = [
    "emails I can't send", "Vicious", "Read your Mind", "Tornado Warnings",
    "because I liked a boy", "Already Over", "how many things", "bet u wanna",
    "Nonsense", "Fast Times", "skinny dipping", "Bad for Business", "decode",
    "opposite", "Feather", "Lonesome", "things I wish you said"
]

# 处理歌曲名：统一小写、替换字符、去除空格
df["歌曲名"] = (
    df["歌曲名"]
    .str.replace("＆", "&")
    .str.replace("'", "'")
    .str.strip()
    .str.lower()
)

# 处理目标列表：同步格式
short_n_sweet_songs = [
    song.replace("＆", "&").replace("'", "'").strip().lower()
    for song in short_n_sweet_songs
]
emails_i_cant_send_songs = [
    song.replace("＆", "&").replace("'", "'").strip().lower()
    for song in emails_i_cant_send_songs
]

# 添加排序字段
short_n_sweet_mapping = {song: idx for idx, song in enumerate(short_n_sweet_songs)}
emails_mapping = {song: idx for idx, song in enumerate(emails_i_cant_send_songs)}

# 过滤并排序数据
filtered_short_n_sweet_df = df[df["歌曲名"].isin(short_n_sweet_songs)].copy()
filtered_short_n_sweet_df["sort_order"] = filtered_short_n_sweet_df["歌曲名"].map(short_n_sweet_mapping)
filtered_short_n_sweet_df = filtered_short_n_sweet_df.sort_values("sort_order")

filtered_emails_df = df[df["歌曲名"].isin(emails_i_cant_send_songs)].copy()
filtered_emails_df["sort_order"] = filtered_emails_df["歌曲名"].map(emails_mapping)
filtered_emails_df = filtered_emails_df.sort_values("sort_order")

# 处理播放量数据
filtered_short_n_sweet_df["总播放量"] = filtered_short_n_sweet_df["总播放量"].fillna(0).astype(int)
filtered_short_n_sweet_df["每日播放量"] = filtered_short_n_sweet_df["每日播放量"].fillna(0).astype(int)
filtered_emails_df["总播放量"] = filtered_emails_df["总播放量"].fillna(0).astype(int)
filtered_emails_df["每日播放量"] = filtered_emails_df["每日播放量"].fillna(0).astype(int)

# 在开始处理数据之前，确保表结构正确
create_table_sql = """
CREATE TABLE IF NOT EXISTS short_n_sweet (
    日期 DATE,
    歌曲名 VARCHAR(255),
    总播放量 BIGINT,
    每日播放量 BIGINT,
    sort_order INT,
    日增变化百分比 DECIMAL(10,2),
    PRIMARY KEY (日期, 歌曲名)
);
"""
cursor.execute(create_table_sql)
conn.commit()

# 插入 short_n_sweet 数据
for _, row in filtered_short_n_sweet_df.iterrows():
    sql = """
    INSERT INTO short_n_sweet (日期, 歌曲名, 总播放量, 每日播放量, sort_order) 
    VALUES (%s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE 
        总播放量 = VALUES(总播放量),
        每日播放量 = VALUES(每日播放量),
        sort_order = VALUES(sort_order);
    """
    cursor.execute(sql, (
        current_date, row["歌曲名"], row["总播放量"],
        row["每日播放量"], row["sort_order"]
    ))

# 计算变化百分比部分的修改
for _, row in filtered_short_n_sweet_df.iterrows():
    try:
        print(f"正在处理歌曲: {row['歌曲名']}")
        current_streams = row["每日播放量"]
        
        # 查询前一天的播放量
        sql = """
        SELECT 每日播放量 
        FROM short_n_sweet 
        WHERE 歌曲名 = %s AND 日期 = %s
        """
        cursor.execute(sql, (row["歌曲名"], previous_date))
        result = cursor.fetchone()
        
        print(f"前一天 ({previous_date}) 的播放量查询结果: {result}")
        print(f"当天 ({current_date}) 的播放量: {current_streams}")

        # 计算日增变化百分比
        if result and result[0] is not None:  # 确保结果存在且不为None
            previous_streams = result[0]
            if previous_streams > 0:
                percentage_change = ((current_streams - previous_streams) / previous_streams) * 100
                print(f"计算过程: ({current_streams} - {previous_streams}) / {previous_streams} * 100")
            else:
                percentage_change = 0
                print("前一天播放量为0，变化率设为0")
        else:
            percentage_change = 0
            print(f"警告：未找到歌曲 {row['歌曲名']} 在 {previous_date} 的数据")

        print(f"计算得到的日增变化百分比: {percentage_change:.2f}%")

        # 插入数据时也包含变化百分比
        sql = """
        INSERT INTO short_n_sweet (日期, 歌曲名, 总播放量, 每日播放量, sort_order, 日增变化百分比) 
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
            总播放量 = VALUES(总播放量),
            每日播放量 = VALUES(每日播放量),
            sort_order = VALUES(sort_order),
            日增变化百分比 = VALUES(日增变化百分比);
        """
        
        cursor.execute(sql, (
            current_date, row["歌曲名"], row["总播放量"],
            current_streams, row["sort_order"], percentage_change
        ))
        
        # 立即提交每条数据
        conn.commit()
        
        # 验证数据是否正确插入
        verify_sql = """
        SELECT 每日播放量, 日增变化百分比 
        FROM short_n_sweet 
        WHERE 日期 = %s AND 歌曲名 = %s
        """
        cursor.execute(verify_sql, (current_date, row["歌曲名"]))
        verify_result = cursor.fetchone()
        print(f"验证插入结果: 每日播放量 = {verify_result[0]}, 日增变化百分比 = {verify_result[1]}%\n")
        
    except Exception as e:
        print(f"处理歌曲 {row['歌曲名']} 时发生错误: {str(e)}")
        conn.rollback()  # 发生错误时回滚


# 在开始之前，先修改 emails_i_cant_send 表结构
create_table_sql = """
CREATE TABLE IF NOT EXISTS emails_i_cant_send (
    日期 DATE,
    歌曲名 VARCHAR(255),
    总播放量 BIGINT,
    每日播放量 BIGINT,
    sort_order INT,
    日增变化百分比 DECIMAL(10,2),
    PRIMARY KEY (日期, 歌曲名)
);
"""
cursor.execute(create_table_sql)
conn.commit()

# 插入 emails_i_cant_send 数据并计算日增变化百分比
for _, row in filtered_emails_df.iterrows():
    try:
        print(f"正在处理歌曲: {row['歌曲名']}")
        current_streams = row["每日播放量"]
        
        # 查询前一天的播放量
        sql = """
        SELECT 每日播放量 
        FROM emails_i_cant_send 
        WHERE 歌曲名 = %s AND 日期 = %s
        """
        cursor.execute(sql, (row["歌曲名"], previous_date))
        result = cursor.fetchone()
        
        print(f"前一天 ({previous_date}) 的播放量查询结果: {result}")
        print(f"当天 ({current_date}) 的播放量: {current_streams}")

        # 计算日增变化百分比
        if result and result[0] is not None:
            previous_streams = result[0]
            if previous_streams > 0:
                percentage_change = ((current_streams - previous_streams) / previous_streams) * 100
                print(f"计算过程: ({current_streams} - {previous_streams}) / {previous_streams} * 100")
            else:
                percentage_change = 0
                print("前一天播放量为0，变化率设为0")
        else:
            percentage_change = 0
            print(f"警告：未找到歌曲 {row['歌曲名']} 在 {previous_date} 的数据")

        print(f"计算得到的日增变化百分比: {percentage_change:.2f}%")

        # 插入数据时也包含变化百分比
        sql = """
        INSERT INTO emails_i_cant_send (日期, 歌曲名, 总播放量, 每日播放量, sort_order, 日增变化百分比) 
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
            总播放量 = VALUES(总播放量),
            每日播放量 = VALUES(每日播放量),
            sort_order = VALUES(sort_order),
            日增变化百分比 = VALUES(日增变化百分比);
        """
        
        cursor.execute(sql, (
            current_date, row["歌曲名"], row["总播放量"],
            current_streams, row["sort_order"], percentage_change
        ))
        
        # 立即提交每条数据
        conn.commit()
        
        # 验证数据是否正确插入
        verify_sql = """
        SELECT 每日播放量, 日增变化百分比 
        FROM emails_i_cant_send 
        WHERE 日期 = %s AND 歌曲名 = %s
        """
        cursor.execute(verify_sql, (current_date, row["歌曲名"]))
        verify_result = cursor.fetchone()
        print(f"验证插入结果: 每日播放量 = {verify_result[0]}, 日增变化百分比 = {verify_result[1]}%\n")
        
    except Exception as e:
        print(f"处理歌曲 {row['歌曲名']} 时发生错误: {str(e)}")
        conn.rollback()  # 发生错误时回滚

# 提交并关闭连接
conn.commit()
cursor.close()
conn.close()

print(f"数据已存入 MySQL，日期：{current_date} ✅")