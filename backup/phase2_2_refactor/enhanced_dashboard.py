"""
향상된 로또 예측 대시보드
- 회차별 모든 예측 표시
- 당첨번호 비교 분석
- 성능 통계 시각화
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from flask import Flask, render_template_string, jsonify, request
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)

class EnhancedLottoDashboard:
    """향상된 로또 대시보드"""
    
    def __init__(self):
        self.db_path = "data/combinations.db"
        self.predictions_db_path = "data/predictions/predictions.db"
        self.logger = logging.getLogger(__name__)
    
    def get_all_rounds(self) -> List[int]:
        """모든 회차 번호 조회"""
        try:
            with sqlite3.connect(self.predictions_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT DISTINCT round 
                    FROM predictions 
                    ORDER BY round DESC
                """)
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"회차 조회 실패: {e}")
            return []
    
    def get_predictions_by_round(self, round_num: int) -> Dict:
        """특정 회차의 모든 예측 조회"""
        try:
            with sqlite3.connect(self.predictions_db_path) as conn:
                cursor = conn.cursor()
                
                # 예측 조회
                cursor.execute("""
                    SELECT id, set_number, numbers, confidence, source, 
                           characteristics, prediction_date
                    FROM predictions
                    WHERE round = ?
                    ORDER BY set_number
                """, (round_num,))
                
                predictions = []
                for row in cursor.fetchall():
                    predictions.append({
                        'id': row[0],
                        'set_number': row[1],
                        'numbers': [int(n) for n in row[2].split(',')],
                        'confidence': row[3],
                        'source': row[4],
                        'characteristics': json.loads(row[5]) if row[5] else {},
                        'date': row[6]
                    })
                
                # 당첨번호 조회
                winning_numbers = self.get_winning_numbers(round_num)
                
                # 결과 분석
                if winning_numbers:
                    for pred in predictions:
                        pred['matches'] = self.check_matches(
                            pred['numbers'], 
                            winning_numbers['numbers']
                        )
                        pred['bonus_match'] = winning_numbers['bonus'] in pred['numbers']
                        pred['rank'] = self.calculate_rank(
                            pred['matches'], 
                            pred['bonus_match']
                        )
                
                return {
                    'round': round_num,
                    'predictions': predictions,
                    'winning_numbers': winning_numbers,
                    'total_predictions': len(predictions),
                    'analysis': self.analyze_round_performance(predictions, winning_numbers)
                }
                
        except Exception as e:
            self.logger.error(f"예측 조회 실패: {e}")
            return {}
    
    def get_winning_numbers(self, round_num: int) -> Optional[Dict]:
        """당첨번호 조회"""
        try:
            # lotto_numbers.db에서 조회
            lotto_db_path = "data/lotto_numbers.db"
            if os.path.exists(lotto_db_path):
                with sqlite3.connect(lotto_db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT draw_date, numbers
                        FROM lotto_numbers
                        WHERE round = ?
                    """, (round_num,))
                    
                    row = cursor.fetchone()
                    if row:
                        numbers_str = row[1]
                        # "1,2,3,4,5,6,7" 형식에서 번호와 보너스 분리
                        all_numbers = [int(n) for n in numbers_str.split(',')]
                        if len(all_numbers) >= 7:
                            return {
                                'date': row[0],
                                'numbers': all_numbers[:6],
                                'bonus': all_numbers[6]
                            }
            
            # 없으면 API나 크롤링으로 가져오기 (추후 구현)
            return None
                
        except Exception as e:
            self.logger.error(f"당첨번호 조회 실패: {e}")
            return None
    
    def check_matches(self, prediction: List[int], winning: List[int]) -> int:
        """일치하는 번호 개수 확인"""
        return len(set(prediction) & set(winning))
    
    def calculate_rank(self, matches: int, bonus_match: bool) -> Optional[int]:
        """등수 계산"""
        if matches == 6:
            return 1
        elif matches == 5 and bonus_match:
            return 2
        elif matches == 5:
            return 3
        elif matches == 4:
            return 4
        elif matches == 3:
            return 5
        return None
    
    def analyze_round_performance(self, predictions: List[Dict], winning_numbers: Dict) -> Dict:
        """회차별 성능 분석"""
        if not winning_numbers or not predictions:
            return {}
        
        ranks = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        total_matches = 0
        best_match = 0
        
        for pred in predictions:
            if 'matches' in pred:
                total_matches += pred['matches']
                best_match = max(best_match, pred['matches'])
                if pred.get('rank'):
                    ranks[pred['rank']] += 1
        
        return {
            'average_matches': total_matches / len(predictions) if predictions else 0,
            'best_match': best_match,
            'rank_distribution': ranks,
            'winning_predictions': sum(ranks.values()),
            'winning_rate': (sum(ranks.values()) / len(predictions) * 100) if predictions else 0
        }
    
    def get_overall_statistics(self) -> Dict:
        """전체 통계 조회"""
        try:
            with sqlite3.connect(self.predictions_db_path) as conn:
                cursor = conn.cursor()
                
                # 전체 예측 수
                cursor.execute("SELECT COUNT(*) FROM predictions")
                total_predictions = cursor.fetchone()[0]
                
                # 회차 수
                cursor.execute("SELECT COUNT(DISTINCT round) FROM predictions")
                total_rounds = cursor.fetchone()[0]
                
                # 당첨 통계 (추후 업데이트)
                cursor.execute("""
                    SELECT 
                        SUM(CASE WHEN rank = 1 THEN 1 ELSE 0 END) as rank1,
                        SUM(CASE WHEN rank = 2 THEN 1 ELSE 0 END) as rank2,
                        SUM(CASE WHEN rank = 3 THEN 1 ELSE 0 END) as rank3,
                        SUM(CASE WHEN rank = 4 THEN 1 ELSE 0 END) as rank4,
                        SUM(CASE WHEN rank = 5 THEN 1 ELSE 0 END) as rank5
                    FROM prediction_results
                """)
                
                row = cursor.fetchone()
                if row and row[0] is not None:
                    rank_stats = {
                        '1등': row[0] or 0,
                        '2등': row[1] or 0,
                        '3등': row[2] or 0,
                        '4등': row[3] or 0,
                        '5등': row[4] or 0
                    }
                else:
                    rank_stats = {'1등': 0, '2등': 0, '3등': 0, '4등': 0, '5등': 0}
                
                return {
                    'total_predictions': total_predictions,
                    'total_rounds': total_rounds,
                    'avg_predictions_per_round': total_predictions / total_rounds if total_rounds > 0 else 0,
                    'rank_distribution': rank_stats,
                    'total_wins': sum(rank_stats.values())
                }
                
        except Exception as e:
            self.logger.error(f"통계 조회 실패: {e}")
            return {}
    
    def get_recent_performance(self, limit: int = 10) -> List[Dict]:
        """최근 회차별 성능"""
        try:
            rounds = self.get_all_rounds()[:limit]
            performance = []
            
            for round_num in rounds:
                data = self.get_predictions_by_round(round_num)
                if data and data.get('winning_numbers'):
                    performance.append({
                        'round': round_num,
                        'date': data['winning_numbers']['date'],
                        'predictions': data['total_predictions'],
                        'analysis': data.get('analysis', {})
                    })
            
            return performance
            
        except Exception as e:
            self.logger.error(f"최근 성능 조회 실패: {e}")
            return []


# HTML 템플릿
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>로또 예측 분석 대시보드</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1600px;
            margin: 0 auto;
        }
        
        header {
            background: white;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        
        h1 {
            color: #667eea;
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .controls {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
            align-items: center;
        }
        
        select, button {
            padding: 10px 20px;
            border-radius: 8px;
            border: 2px solid #667eea;
            font-size: 16px;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        select:hover, button:hover {
            background: #667eea;
            color: white;
        }
        
        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        
        .card {
            background: white;
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        
        .card h2 {
            color: #667eea;
            margin-bottom: 15px;
            font-size: 1.5em;
            border-bottom: 2px solid #eee;
            padding-bottom: 10px;
        }
        
        .number-ball {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            margin: 2px;
            font-weight: bold;
            color: white;
            background: linear-gradient(135deg, #667eea, #764ba2);
        }
        
        .bonus-ball {
            background: linear-gradient(135deg, #f093fb, #f5576c);
        }
        
        .match-0 { background: #ddd; color: #666; }
        .match-1 { background: #a0c4ff; }
        .match-2 { background: #72d572; }
        .match-3 { background: #ffd700; color: #333; }
        .match-4 { background: #ff9500; }
        .match-5 { background: #ff6b6b; }
        .match-6 { background: #ff0000; }
        
        .prediction-item {
            padding: 15px;
            margin: 10px 0;
            border-radius: 10px;
            background: #f8f9fa;
            transition: transform 0.2s;
        }
        
        .prediction-item:hover {
            transform: translateX(5px);
            box-shadow: 0 3px 10px rgba(0,0,0,0.1);
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            margin-top: 15px;
        }
        
        .stat-item {
            text-align: center;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        
        .stat-value {
            font-size: 24px;
            font-weight: bold;
            color: #667eea;
        }
        
        .stat-label {
            font-size: 12px;
            color: #666;
            margin-top: 5px;
        }
        
        .winning-badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 5px;
            font-size: 12px;
            font-weight: bold;
            margin-left: 10px;
        }
        
        .rank-1 { background: #ff0000; color: white; }
        .rank-2 { background: #ff6b6b; color: white; }
        .rank-3 { background: #ffd700; color: #333; }
        .rank-4 { background: #72d572; color: white; }
        .rank-5 { background: #a0c4ff; color: white; }
        
        .loading {
            text-align: center;
            padding: 20px;
            color: #666;
        }
        
        .performance-chart {
            margin-top: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 10px;
        }
        
        #winningNumbers {
            background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%);
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>로또 예측 분석 대시보드</h1>
            <div class="controls">
                <select id="roundSelect">
                    <option value="">회차 선택...</option>
                </select>
                <button onclick="loadRoundData()">조회</button>
                <button onclick="loadLatestRound()">최신 회차</button>
                <button onclick="showStatistics()">전체 통계</button>
            </div>
        </header>
        
        <div id="winningNumbers" style="display: none;">
            <h3>당첨번호</h3>
            <div id="winningNumbersContent"></div>
        </div>
        
        <div class="dashboard-grid">
            <!-- 예측 목록 -->
            <div class="card" style="grid-column: span 2;">
                <h2>예측 번호 분석</h2>
                <div id="predictionsContent">
                    <div class="loading">회차를 선택해주세요...</div>
                </div>
            </div>
            
            <!-- 통계 -->
            <div class="card">
                <h2>회차 통계</h2>
                <div id="roundStats">
                    <div class="loading">통계를 불러오는 중...</div>
                </div>
            </div>
            
            <!-- 성능 차트 -->
            <div class="card">
                <h2>최근 성능</h2>
                <div id="performanceChart">
                    <div class="loading">데이터를 불러오는 중...</div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let currentRound = null;
        
        // 페이지 로드 시 초기화
        window.onload = function() {
            loadRounds();
            loadRecentPerformance();
        };
        
        // 회차 목록 로드
        function loadRounds() {
            fetch('/api/rounds')
                .then(response => response.json())
                .then(data => {
                    const select = document.getElementById('roundSelect');
                    select.innerHTML = '<option value="">회차 선택...</option>';
                    
                    data.rounds.forEach(round => {
                        const option = document.createElement('option');
                        option.value = round;
                        option.textContent = `${round}회차`;
                        select.appendChild(option);
                    });
                    
                    if (data.rounds.length > 0) {
                        select.value = data.rounds[0];
                        loadRoundData();
                    }
                })
                .catch(error => console.error('Error:', error));
        }
        
        // 회차 데이터 로드
        function loadRoundData() {
            const round = document.getElementById('roundSelect').value;
            if (!round) return;
            
            currentRound = round;
            
            fetch(`/api/predictions/${round}`)
                .then(response => response.json())
                .then(data => {
                    displayWinningNumbers(data.winning_numbers);
                    displayPredictions(data.predictions, data.winning_numbers);
                    displayRoundStats(data.analysis, data.total_predictions);
                })
                .catch(error => console.error('Error:', error));
        }
        
        // 당첨번호 표시
        function displayWinningNumbers(winning) {
            const container = document.getElementById('winningNumbers');
            const content = document.getElementById('winningNumbersContent');
            
            if (!winning) {
                container.style.display = 'none';
                return;
            }
            
            container.style.display = 'block';
            content.innerHTML = `
                <div style="margin-top: 10px;">
                    <span style="color: #333; margin-right: 10px;">추첨일: ${winning.date}</span>
                    ${winning.numbers.map(n => 
                        `<span class="number-ball">${n}</span>`
                    ).join('')}
                    <span class="number-ball bonus-ball">+${winning.bonus}</span>
                </div>
            `;
        }
        
        // 예측 표시
        function displayPredictions(predictions, winning) {
            const container = document.getElementById('predictionsContent');
            
            if (!predictions || predictions.length === 0) {
                container.innerHTML = '<div class="loading">예측 데이터가 없습니다.</div>';
                return;
            }
            
            let html = '';
            predictions.forEach(pred => {
                const matchClass = pred.matches !== undefined ? `match-${pred.matches}` : '';
                const rankBadge = pred.rank ? `<span class="winning-badge rank-${pred.rank}">${pred.rank}등</span>` : '';
                
                html += `
                    <div class="prediction-item">
                        <div style="margin-bottom: 10px;">
                            <strong>Set ${pred.set_number}</strong>
                            <span style="color: #666; margin-left: 10px;">${pred.source}</span>
                            <span style="color: #667eea; margin-left: 10px;">신뢰도: ${(pred.confidence * 100).toFixed(1)}%</span>
                            ${rankBadge}
                        </div>
                        <div>
                            ${pred.numbers.map(n => {
                                let ballClass = 'number-ball';
                                if (winning && winning.numbers) {
                                    if (winning.numbers.includes(n)) {
                                        ballClass += ' ' + matchClass;
                                    }
                                }
                                return `<span class="${ballClass}">${n}</span>`;
                            }).join('')}
                            ${pred.matches !== undefined ? 
                                `<span style="margin-left: 10px; color: #666;">일치: ${pred.matches}개</span>` : ''}
                        </div>
                        ${pred.characteristics ? `
                            <div style="margin-top: 10px; font-size: 12px; color: #666;">
                                홀/짝: ${pred.characteristics.odd_even_ratio || '-'} | 
                                합계: ${pred.characteristics.sum_total || '-'} | 
                                연속: ${pred.characteristics.consecutive_count || 0}개
                            </div>
                        ` : ''}
                    </div>
                `;
            });
            
            container.innerHTML = html;
        }
        
        // 회차 통계 표시
        function displayRoundStats(analysis, total) {
            const container = document.getElementById('roundStats');
            
            if (!analysis) {
                container.innerHTML = '<div class="loading">통계 데이터가 없습니다.</div>';
                return;
            }
            
            container.innerHTML = `
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-value">${total}</div>
                        <div class="stat-label">전체 예측</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">${analysis.average_matches.toFixed(2)}</div>
                        <div class="stat-label">평균 일치</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">${analysis.best_match}</div>
                        <div class="stat-label">최고 일치</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">${analysis.winning_rate.toFixed(1)}%</div>
                        <div class="stat-label">당첨률</div>
                    </div>
                </div>
                ${analysis.rank_distribution ? `
                    <div class="performance-chart">
                        <h4>등수 분포</h4>
                        <div class="stats-grid">
                            ${Object.entries(analysis.rank_distribution).map(([rank, count]) => `
                                <div class="stat-item">
                                    <div class="stat-value">${count}</div>
                                    <div class="stat-label">${rank}등</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                ` : ''}
            `;
        }
        
        // 최신 회차 로드
        function loadLatestRound() {
            const select = document.getElementById('roundSelect');
            if (select.options.length > 1) {
                select.selectedIndex = 1;
                loadRoundData();
            }
        }
        
        // 최근 성능 로드
        function loadRecentPerformance() {
            fetch('/api/performance')
                .then(response => response.json())
                .then(data => {
                    displayPerformanceChart(data.performance);
                })
                .catch(error => console.error('Error:', error));
        }
        
        // 성능 차트 표시
        function displayPerformanceChart(performance) {
            const container = document.getElementById('performanceChart');
            
            if (!performance || performance.length === 0) {
                container.innerHTML = '<div class="loading">성능 데이터가 없습니다.</div>';
                return;
            }
            
            let html = '<div style="max-height: 300px; overflow-y: auto;">';
            performance.forEach(item => {
                html += `
                    <div style="padding: 10px; border-bottom: 1px solid #eee;">
                        <strong>${item.round}회차</strong>
                        <span style="color: #666; margin-left: 10px;">${item.date}</span>
                        <div style="margin-top: 5px; font-size: 14px;">
                            예측: ${item.predictions}개 | 
                            평균: ${item.analysis.average_matches ? item.analysis.average_matches.toFixed(2) : '-'}개 | 
                            최고: ${item.analysis.best_match || '-'}개
                        </div>
                    </div>
                `;
            });
            html += '</div>';
            
            container.innerHTML = html;
        }
        
        // 전체 통계 표시
        function showStatistics() {
            fetch('/api/statistics')
                .then(response => response.json())
                .then(data => {
                    alert(`전체 통계\\n\\n` +
                          `총 예측: ${data.total_predictions}개\\n` +
                          `총 회차: ${data.total_rounds}회\\n` +
                          `회차당 평균: ${data.avg_predictions_per_round.toFixed(1)}개\\n` +
                          `총 당첨: ${data.total_wins}개`);
                })
                .catch(error => console.error('Error:', error));
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """메인 대시보드 페이지"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/rounds')
def api_rounds():
    """회차 목록 API"""
    dashboard = EnhancedLottoDashboard()
    rounds = dashboard.get_all_rounds()
    return jsonify({'rounds': rounds})

@app.route('/api/predictions/<int:round_num>')
def api_predictions(round_num):
    """특정 회차 예측 API"""
    dashboard = EnhancedLottoDashboard()
    data = dashboard.get_predictions_by_round(round_num)
    return jsonify(data)

@app.route('/api/performance')
def api_performance():
    """최근 성능 API"""
    dashboard = EnhancedLottoDashboard()
    performance = dashboard.get_recent_performance()
    return jsonify({'performance': performance})

@app.route('/api/statistics')
def api_statistics():
    """전체 통계 API"""
    dashboard = EnhancedLottoDashboard()
    stats = dashboard.get_overall_statistics()
    return jsonify(stats)

def run_enhanced_dashboard(host='127.0.0.1', port=5001, debug=False):
    """향상된 대시보드 실행"""
    print("\n" + "="*60)
    print("Enhanced Lotto Prediction Dashboard")
    print("="*60)
    print(f"\n[INFO] Starting web server...")
    print(f"[INFO] Open browser: http://{host}:{port}")
    print(f"[INFO] Press Ctrl+C to stop.\n")
    print("\nMain Features:")
    print("  - View all predictions by round")
    print("  - Compare with winning numbers")
    print("  - Visualize match counts")
    print("  - Auto calculate rankings")
    print("  - Performance statistics")
    print("="*60 + "\n")
    
    app.run(host=host, port=port, debug=debug)

if __name__ == '__main__':
    run_enhanced_dashboard(debug=True)