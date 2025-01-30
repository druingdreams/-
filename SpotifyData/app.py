from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
import pymysql
from getSpotifyDailyData import SpotifyChartScraper
import pandas as pd
import logging

app = Flask(__name__)

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '1234',
    'database': 'spotify_data'
}

def get_db_connection():
    """创建数据库连接"""
    return pymysql.connect(**DB_CONFIG)

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/start_scraping', methods=['POST'])
def start_scraping():
    """启动爬虫"""
    try:
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        
        scraper = SpotifyChartScraper(start_date=start_date, end_date=end_date)
        scraper.run()
        
        return jsonify({'status': 'success', 'message': '数据爬取完成'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/get_chart_data')
def get_chart_data():
    """获取图表数据"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取最新日期的排行榜数据
        cursor.execute("""
            SELECT date, track_name, singer, streams, chart_rank 
            FROM spotify_charts 
            WHERE date = (SELECT MAX(date) FROM spotify_charts)
            ORDER BY chart_rank LIMIT 50
        """)
        
        data = cursor.fetchall()
        return jsonify({
            'status': 'success',
            'data': [{
                'date': row[0].strftime('%Y-%m-%d'),
                'track_name': row[1],
                'singer': row[2],
                'streams': row[3],
                'rank': row[4]
            } for row in data]
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        cursor.close()
        conn.close()

@app.route('/search', methods=['POST'])
def search():
    try:
        search_type = request.form.get('search_type')
        search_term = request.form.get('search_term')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        print(f"搜索参数: type={search_type}, term={search_term}, start={start_date}, end={end_date}")

        conn = get_db_connection()
        cursor = conn.cursor()

        if search_type == 'song':
            query = """
            WITH combined_data AS (
                SELECT date, track_name, singer, streams, chart_rank
                FROM (
                    SELECT date, track_name, singer, streams, chart_rank
                    FROM spotify_charts
                    WHERE track_name = %s
                    AND date BETWEEN %s AND %s
                    UNION ALL
                    SELECT date, track_name, singer, streams, chart_rank
                    FROM spotify_charts1
                    WHERE track_name = %s
                    AND date BETWEEN %s AND %s
                ) all_data
                ORDER BY date
            ),
            daily_change AS (
                SELECT 
                    date,
                    track_name,
                    singer,
                    streams,
                    chart_rank,
                    LAG(streams) OVER (ORDER BY date) as prev_streams,
                    LAG(date) OVER (ORDER BY date) as prev_date
                FROM combined_data
            )
            SELECT 
                date,
                track_name,
                singer,
                streams,
                chart_rank,
                CASE 
                    WHEN prev_streams IS NULL THEN NULL
                    WHEN prev_streams = 0 THEN NULL
                    WHEN DATEDIFF(date, prev_date) > 1 THEN NULL
                    ELSE ROUND(((streams - prev_streams) * 100.0 / prev_streams), 2)
                END as growth_rate
            FROM daily_change
            ORDER BY date DESC
            """
            
            cursor.execute(query, (
                search_term, start_date, end_date,
                search_term, start_date, end_date
            ))
            
            results = cursor.fetchall()
            print(f"查询结果数量: {len(results)}")
            
            if results:
                print(f"第一条记录: {results[0]}")

            data = [{
                'date': row[0].strftime('%Y-%m-%d') if row[0] else '',
                'track_name': row[1],
                'singer': row[2],
                'streams': row[3],
                'rank': row[4],
                'growth_rate': float(row[5]) if row[5] is not None else None
            } for row in results]

            if data:
                print(f"处理后的第一条记录: {data[0]}")

            return jsonify({
                'status': 'success',
                'data': data,
                'search_type': 'song',
                'total_days': len(results)
            })
        else:
            query = """
            (SELECT date, track_name, singer, streams, chart_rank
            FROM spotify_charts
            WHERE singer LIKE %s
            AND date BETWEEN %s AND %s)
            UNION
            (SELECT date, track_name, singer, streams, chart_rank
            FROM spotify_charts1
            WHERE singer LIKE %s
            AND date BETWEEN %s AND %s)
            ORDER BY date DESC, streams DESC
            """
            cursor.execute(query, (
                f'%{search_term}%', start_date, end_date,
                f'%{search_term}%', start_date, end_date
            ))
            
            results = cursor.fetchall()
            data = [{
                'date': row[0].strftime('%Y-%m-%d') if row[0] else '',
                'track_name': row[1],
                'singer': row[2],
                'streams': row[3],
                'rank': row[4]
            } for row in results]

            # 获取每日总播放量数据
            daily_total_query = """
            SELECT date, SUM(streams) as total_streams
            FROM (
                SELECT date, streams
                FROM spotify_charts
                WHERE singer LIKE %s
                AND date BETWEEN %s AND %s
                UNION ALL
                SELECT date, streams
                FROM spotify_charts1
                WHERE singer LIKE %s
                AND date BETWEEN %s AND %s
            ) combined_data
            GROUP BY date
            ORDER BY date
            """
            cursor.execute(daily_total_query, (
                f'%{search_term}%', start_date, end_date,
                f'%{search_term}%', start_date, end_date
            ))
            daily_totals = cursor.fetchall()

            # 计算总播放量
            total_streams_query = """
            SELECT SUM(streams) as total_streams
            FROM (
                SELECT streams
                FROM spotify_charts
                WHERE singer LIKE %s
                AND date BETWEEN %s AND %s
                UNION ALL
                SELECT streams
                FROM spotify_charts1
                WHERE singer LIKE %s
                AND date BETWEEN %s AND %s
            ) combined_data
            """
            cursor.execute(total_streams_query, (
                f'%{search_term}%', start_date, end_date,
                f'%{search_term}%', start_date, end_date
            ))
            total_streams = cursor.fetchone()[0] or 0

            # 计算最高播放量
            max_streams_query = """
            SELECT MAX(streams) as max_streams
            FROM (
                SELECT streams
                FROM spotify_charts
                WHERE singer LIKE %s
                AND date BETWEEN %s AND %s
                UNION ALL
                SELECT streams
                FROM spotify_charts1
                WHERE singer LIKE %s
                AND date BETWEEN %s AND %s
            ) combined_data
            """
            cursor.execute(max_streams_query, (
                f'%{search_term}%', start_date, end_date,
                f'%{search_term}%', start_date, end_date
            ))
            max_streams = cursor.fetchone()[0] or 0

            # 计算在榜天数
            total_days_query = """
            SELECT COUNT(DISTINCT date) as total_days
            FROM (
                SELECT date
                FROM spotify_charts
                WHERE singer LIKE %s
                AND date BETWEEN %s AND %s
                UNION
                SELECT date
                FROM spotify_charts1
                WHERE singer LIKE %s
                AND date BETWEEN %s AND %s
            ) combined_data
            """
            cursor.execute(total_days_query, (
                f'%{search_term}%', start_date, end_date,
                f'%{search_term}%', start_date, end_date
            ))
            total_days = cursor.fetchone()[0] or 0

            return jsonify({
                'status': 'success',
                'data': data,
                'search_type': 'artist',
                'total_streams': total_streams,
                'max_streams': max_streams,
                'total_days': total_days,
                'daily_totals': [{
                    'date': row[0].strftime('%Y-%m-%d'),
                    'total_streams': row[1]
                } for row in daily_totals]
            })

    except Exception as e:
        print(f"搜索错误: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        cursor.close()
        conn.close()

@app.route('/get_statistics', methods=['POST'])
def get_statistics():
    try:
        track_name = request.form.get('track_name')
        conn = get_db_connection()
        cursor = conn.cursor()

        # 修正表名为 spotify_charts 和 spotify_charts1
        query = """
        SELECT 
            MAX(streams) as max_streams,
            MIN(chart_rank) as highest_rank,
            COUNT(DISTINCT date) as days_on_chart
        FROM (
            SELECT streams, chart_rank, date
            FROM spotify_charts
            WHERE track_name = %s
            UNION ALL
            SELECT streams, chart_rank, date
            FROM spotify_charts1
            WHERE track_name = %s
        ) combined_data
        """
        cursor.execute(query, (track_name, track_name))
        stats = cursor.fetchone()

        return jsonify({
            'status': 'success',
            'statistics': {
                'max_streams': f"{stats[0]:,}" if stats[0] else "0",
                'highest_rank': stats[1] if stats[1] else "N/A",
                'days_on_chart': stats[2] if stats[2] else 0
            }
        })

    except Exception as e:
        print(f"统计错误: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        cursor.close()
        conn.close()

@app.route('/get_daily_total', methods=['POST'])
def get_daily_total():
    try:
        search_type = request.form.get('search_type')
        search_term = request.form.get('search_term')
        
        conn = get_db_connection()
        cursor = conn.cursor()

        if search_type == 'song':
            query = """
            WITH combined_data AS (
                SELECT date, track_name, singer, streams, chart_rank
                FROM (
                    SELECT date, track_name, singer, streams, chart_rank
                    FROM spotify_charts
                    WHERE track_name = %s
                    AND date BETWEEN %s AND %s
                    UNION ALL
                    SELECT date, track_name, singer, streams, chart_rank
                    FROM spotify_charts1
                    WHERE track_name = %s
                    AND date BETWEEN %s AND %s
                ) all_data
                ORDER BY date
            ),
            daily_change AS (
                SELECT 
                    date,
                    track_name,
                    singer,
                    streams,
                    chart_rank,
                    LAG(streams) OVER (ORDER BY date) as prev_day_streams,
                    LAG(date) OVER (ORDER BY date) as prev_date
                FROM combined_data
            )
            SELECT 
                date,
                track_name,
                singer,
                streams,
                chart_rank,
                CASE 
                    WHEN prev_day_streams IS NULL OR 
                         prev_day_streams = 0 OR 
                         date - prev_date > INTERVAL '1 day' 
                    THEN NULL
                    ELSE ROUND(((streams - prev_day_streams) * 100.0 / prev_day_streams)::numeric, 2)
                END as growth_rate
            FROM daily_change
            ORDER BY date DESC
            """
            cursor.execute(query, (
                search_term, start_date, end_date,
                search_term, start_date, end_date
            ))

            results = cursor.fetchall()
            data = [{
                'date': row[0].strftime('%Y-%m-%d') if row[0] else '',
                'track_name': row[1],
                'singer': row[2],
                'streams': row[3],
                'rank': row[4],
                'growth_rate': row[5]  # 可能为 None
            } for row in results]
        else:
            # 原有的歌手每日总播放量查询逻辑
            query = """
            SELECT date, SUM(streams) as total_streams
            FROM (
                SELECT date, streams, singer
                FROM spotify_charts
                WHERE singer LIKE %s
                UNION ALL
                SELECT date, streams, singer
                FROM spotify_charts1
                WHERE singer LIKE %s
            ) combined_data
            GROUP BY date
            ORDER BY date
            """
            cursor.execute(query, (f'%{search_term}%', f'%{search_term}%'))
        
        results = cursor.fetchall()
        
        if search_type == 'song':
            data = [{
                'date': row[0].strftime('%Y-%m-%d'),
                'growth_rate': round(row[1], 2)
            } for row in results]
        else:
            data = [{
                'date': row[0].strftime('%Y-%m-%d'),
                'total_streams': row[1]
            } for row in results]

        return jsonify({
            'status': 'success',
            'data': data,
            'search_type': search_type
        })

    except Exception as e:
        print(f"获取数据错误: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    app.run(debug=True) 