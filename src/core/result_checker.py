"""
로또 당첨 결과 확인 및 비교 시스템

실제 당첨번호와 예측번호를 비교하고 성과를 분석합니다.
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

class ResultChecker:
    """당첨 결과 확인 클래스"""
    
    def __init__(self, db_manager, prediction_tracker):
        """
        초기화
        
        Args:
            db_manager: 데이터베이스 매니저 (당첨번호 조회용)
            prediction_tracker: 예측 관리자
        """
        self.db_manager = db_manager
        self.prediction_tracker = prediction_tracker
        self.logger = logging.getLogger(__name__)
    
    def check_all_predictions_for_round(self, round_num: int) -> Dict:
        """
        특정 회차의 모든 누적된 예측을 당첨번호와 대조
        
        Args:
            round_num: 확인할 회차 번호
            
        Returns:
            전체 대조 결과
        """
        try:
            # 해당 회차의 모든 예측 조회 (누적된 것 포함)
            predictions = self.prediction_tracker.get_predictions(round_num)
            if not predictions:
                self.logger.info(f"{round_num}회차 예측이 없습니다.")
                return {'status': 'no_predictions', 'round': round_num}
            
            # 실제 당첨번호 조회
            actual_data = self.db_manager.get_numbers_by_round(round_num)
            if not actual_data:
                self.logger.info(f"{round_num}회차 당첨번호가 아직 발표되지 않았습니다.")
                return {'status': 'waiting', 'round': round_num, 'prediction_count': len(predictions)}
            
            # 당첨번호 파싱
            numbers_str = actual_data[1]
            all_numbers = [int(n) for n in numbers_str.split(',')]
            actual_numbers = all_numbers[:6]
            bonus_number = all_numbers[6] if len(all_numbers) > 6 else 0
            
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"📊 {round_num}회차 전체 예측 대조 시작")
            self.logger.info(f"당첨번호: {sorted(actual_numbers)} + 보너스 [{bonus_number}]")
            self.logger.info(f"대조할 예측 수: {len(predictions)}세트")
            self.logger.info(f"{'='*60}")
            
            # 모든 예측과 비교
            results = []
            rank_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            total_prize = 0
            match_distribution = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
            
            for i, pred in enumerate(predictions, 1):
                # 일치 개수 계산
                match_count = len(set(pred['numbers']) & set(actual_numbers))
                bonus_match = bonus_number in pred['numbers']
                
                # 등수 계산
                rank = self.calculate_rank(match_count, bonus_match)
                
                # 당첨금 추정
                prize = self.estimate_prize(rank)
                
                # 결과 저장
                result = {
                    'prediction_id': pred['id'],
                    'set_number': pred['set_number'],
                    'predicted_numbers': pred['numbers'],
                    'match_count': match_count,
                    'bonus_match': bonus_match,
                    'rank': rank,
                    'prize': prize,
                    'source': pred.get('source', 'Unknown'),
                    'confidence': pred.get('confidence', 0.5)
                }
                results.append(result)
                
                # 통계 업데이트
                match_distribution[match_count] += 1
                if rank > 0:
                    rank_distribution[rank] += 1
                    total_prize += prize
                    
                # 당첨 시 로그 출력
                if rank > 0:
                    rank_emoji = {1: "🏆", 2: "🥈", 3: "🥉", 4: "⭐", 5: "✅"}
                    self.logger.info(f"  {rank_emoji.get(rank, '')} 세트 {pred['set_number']}: "
                                   f"{sorted(pred['numbers'])} → {match_count}개 일치, {rank}등 당첨!")
                
                # DB에 결과 저장 (이미 저장된 것은 스킵)
                self._save_result_to_db(round_num, pred['id'], actual_numbers, 
                                       bonus_number, match_count, bonus_match, rank, prize)
            
            # 통계 요약
            total_wins = sum(rank_distribution.values())
            win_rate = (total_wins / len(predictions)) * 100 if predictions else 0
            avg_matches = sum(r['match_count'] for r in results) / len(results)
            
            # 최종 결과 로그
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"📈 대조 결과 요약")
            self.logger.info(f"{'='*60}")
            self.logger.info(f"총 예측: {len(predictions)}세트")
            self.logger.info(f"당첨: {total_wins}세트 ({win_rate:.1f}%)")
            
            if total_wins > 0:
                self.logger.info(f"\n등수별 분포:")
                for rank in range(1, 6):
                    if rank_distribution[rank] > 0:
                        self.logger.info(f"  {rank}등: {rank_distribution[rank]}세트")
                self.logger.info(f"\n총 예상 당첨금: {total_prize:,}원")
            
            self.logger.info(f"\n일치 개수 분포:")
            for match in range(7):
                if match_distribution[match] > 0:
                    self.logger.info(f"  {match}개 일치: {match_distribution[match]}세트")
            
            self.logger.info(f"\n평균 일치 개수: {avg_matches:.2f}개")
            self.logger.info(f"{'='*60}\n")
            
            # 주간 성과 업데이트
            best_rank = min([r for r in rank_distribution if rank_distribution[r] > 0], default=0)
            self._update_weekly_performance(round_num, best_rank, rank_distribution, 
                                           total_prize, avg_matches)
            
            # 상세 보고서 생성
            detailed_report = self.generate_detailed_report(
                round_num, actual_numbers, bonus_number, results, 
                rank_distribution, match_distribution, total_prize
            )
            
            return {
                'status': 'checked',
                'round': round_num,
                'actual_numbers': actual_numbers,
                'bonus_number': bonus_number,
                'total_predictions': len(predictions),
                'total_wins': total_wins,
                'win_rate': win_rate,
                'rank_distribution': rank_distribution,
                'match_distribution': match_distribution,
                'total_prize': total_prize,
                'avg_matches': avg_matches,
                'results': results,
                'report': detailed_report
            }
            
        except Exception as e:
            self.logger.error(f"전체 예측 대조 실패: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {'status': 'error', 'message': str(e)}
    
    def check_new_results(self) -> Dict:
        """
        새 당첨번호 확인 및 비교
        
        Returns:
            확인 결과
        """
        try:
            # 미확인 예측 조회
            unchecked = self.prediction_tracker.get_latest_unchecked()
            if not unchecked:
                self.logger.info("확인할 예측이 없습니다.")
                return {'status': 'no_predictions'}
            
            round_num = unchecked['round']
            # 모든 누적된 예측을 대조하도록 변경
            return self.check_all_predictions_for_round(round_num)
            
            # 실제 당첨번호 조회
            actual_data = self.db_manager.get_numbers_by_round(round_num)
            if not actual_data:
                self.logger.info(f"{round_num}회차 당첨번호가 아직 발표되지 않았습니다.")
                return {'status': 'waiting', 'round': round_num}
            
            # actual_data는 (round, numbers_str, date) 튜플
            numbers_str = actual_data[1]
            # 번호 문자열을 리스트로 변환 (마지막 번호가 보너스)
            all_numbers = [int(n) for n in numbers_str.split(',')]
            actual_numbers = all_numbers[:6]
            bonus_number = all_numbers[6] if len(all_numbers) > 6 else 0
            
            # 각 예측과 비교
            results = []
            best_rank = 0
            total_prize = 0
            total_matches = 0
            rank_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            
            for pred in predictions:
                # 일치 개수 계산
                match_count = len(set(pred['numbers']) & set(actual_numbers))
                bonus_match = bonus_number in pred['numbers']
                
                # 등수 계산
                rank = self.calculate_rank(match_count, bonus_match)
                
                # 당첨금 추정
                prize = self.estimate_prize(rank)
                
                # 결과 저장
                result = {
                    'prediction_id': pred['id'],
                    'set_number': pred['set_number'],
                    'predicted_numbers': pred['numbers'],
                    'match_count': match_count,
                    'bonus_match': bonus_match,
                    'rank': rank,
                    'prize': prize
                }
                results.append(result)
                
                # 통계 업데이트
                if rank > 0:
                    rank_counts[rank] += 1
                    if rank > best_rank or best_rank == 0:
                        best_rank = rank
                    total_prize += prize
                
                total_matches += match_count
                
                # DB에 결과 저장
                self._save_result_to_db(round_num, pred['id'], actual_numbers, 
                                       bonus_number, match_count, bonus_match, rank, prize)
            
            # 주간 성과 업데이트
            accuracy_rate = total_matches / len(predictions) if predictions else 0
            self._update_weekly_performance(round_num, best_rank, rank_counts, 
                                           total_prize, accuracy_rate)
            
            # JSON 결과 업데이트
            self._update_json_result(round_num, actual_numbers, bonus_number, results)
            
            # 결과 보고서 생성
            report = self.generate_report(round_num, actual_numbers, bonus_number, 
                                        results, rank_counts, total_prize)
            
            return {
                'status': 'checked',
                'round': round_num,
                'actual_numbers': actual_numbers,
                'bonus_number': bonus_number,
                'results': results,
                'best_rank': best_rank,
                'total_prize': total_prize,
                'accuracy_rate': accuracy_rate,
                'report': report
            }
            
        except Exception as e:
            self.logger.error(f"결과 확인 실패: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def calculate_rank(self, match_count: int, bonus_match: bool = False) -> int:
        """
        등수 계산
        
        Args:
            match_count: 일치 개수
            bonus_match: 보너스 번호 일치 여부
        
        Returns:
            등수 (1-5, 0=미당첨)
        """
        if match_count == 6:
            return 1  # 1등
        elif match_count == 5 and bonus_match:
            return 2  # 2등
        elif match_count == 5:
            return 3  # 3등
        elif match_count == 4:
            return 4  # 4등
        elif match_count == 3:
            return 5  # 5등
        else:
            return 0  # 미당첨
    
    def estimate_prize(self, rank: int) -> int:
        """
        예상 당첨금 계산
        
        Args:
            rank: 등수
        
        Returns:
            예상 당첨금
        """
        # 평균 당첨금 기준 (실제와 다를 수 있음)
        prize_map = {
            1: 2000000000,  # 20억 (평균)
            2: 50000000,    # 5천만원
            3: 1500000,     # 150만원
            4: 50000,       # 5만원
            5: 5000,        # 5천원
            0: 0
        }
        return prize_map.get(rank, 0)
    
    def _save_result_to_db(self, round_num: int, prediction_id: int, 
                           actual_numbers: List[int], bonus_number: int,
                           match_count: int, bonus_match: bool, 
                           rank: int, prize: int):
        """데이터베이스에 결과 저장"""
        try:
            with sqlite3.connect(self.prediction_tracker.db_path) as conn:
                cursor = conn.cursor()
                
                numbers_str = ','.join(map(str, actual_numbers))
                cursor.execute("""
                    INSERT INTO prediction_results
                    (round, prediction_id, actual_numbers, bonus_number, 
                     match_count, bonus_match, rank, prize_amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (round_num, prediction_id, numbers_str, bonus_number,
                     match_count, 1 if bonus_match else 0, rank, prize))
                
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"결과 저장 실패: {e}")
    
    def _update_weekly_performance(self, round_num: int, best_rank: int,
                                  rank_counts: Dict, total_prize: int,
                                  accuracy_rate: float):
        """주간 성과 업데이트"""
        try:
            with sqlite3.connect(self.prediction_tracker.db_path) as conn:
                cursor = conn.cursor()
                
                # 최고 일치 개수 계산
                best_match = 0
                if best_rank == 1:
                    best_match = 6
                elif best_rank == 2 or best_rank == 3:
                    best_match = 5
                elif best_rank == 4:
                    best_match = 4
                elif best_rank == 5:
                    best_match = 3
                
                cursor.execute("""
                    UPDATE weekly_performance
                    SET checked = 1,
                        best_match = ?,
                        best_rank = ?,
                        rank_1_count = ?,
                        rank_2_count = ?,
                        rank_3_count = ?,
                        rank_4_count = ?,
                        rank_5_count = ?,
                        total_prize = ?,
                        accuracy_rate = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE round = ?
                """, (best_match, best_rank,
                     rank_counts.get(1, 0), rank_counts.get(2, 0),
                     rank_counts.get(3, 0), rank_counts.get(4, 0),
                     rank_counts.get(5, 0), total_prize, accuracy_rate,
                     round_num))
                
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"주간 성과 업데이트 실패: {e}")
    
    def _update_json_result(self, round_num: int, actual_numbers: List[int],
                           bonus_number: int, results: List[Dict]):
        """JSON 파일 결과 업데이트"""
        try:
            year = datetime.now().year
            json_path = self.prediction_tracker.db_path.parent / str(year) / f"week_{round_num}.json"
            
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 결과 업데이트
                data['result'] = {
                    'checked': True,
                    'check_date': datetime.now().isoformat(),
                    'actual_numbers': actual_numbers,
                    'bonus_number': bonus_number,
                    'matches': [],
                    'best_rank': 0,
                    'total_prize': 0
                }
                
                for result in results:
                    data['result']['matches'].append({
                        'set': result['set_number'],
                        'match_count': result['match_count'],
                        'bonus_match': result['bonus_match'],
                        'rank': result['rank'],
                        'prize': result['prize']
                    })
                    
                    if result['rank'] > 0:
                        if result['rank'] < data['result']['best_rank'] or data['result']['best_rank'] == 0:
                            data['result']['best_rank'] = result['rank']
                        data['result']['total_prize'] += result['prize']
                
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    
        except Exception as e:
            self.logger.error(f"JSON 결과 업데이트 실패: {e}")
    
    def generate_detailed_report(self, round_num: int, actual_numbers: List[int],
                                bonus_number: int, results: List[Dict],
                                rank_distribution: Dict, match_distribution: Dict,
                                total_prize: int) -> str:
        """
        상세한 대조 결과 보고서 생성
        
        Returns:
            포맷된 상세 보고서 문자열
        """
        report = []
        report.append("=" * 60)
        report.append(f"📊 {round_num}회차 전체 예측 대조 결과")
        report.append("=" * 60)
        report.append(f"당첨번호: {sorted(actual_numbers)} + 보너스 [{bonus_number}]")
        report.append(f"총 예측 수: {len(results)}세트")
        report.append("")
        
        # 당첨 예측 먼저 표시
        winning_predictions = [r for r in results if r['rank'] > 0]
        if winning_predictions:
            report.append("🎊 당첨 예측")
            report.append("-" * 60)
            for result in sorted(winning_predictions, key=lambda x: x['rank']):
                set_num = result['set_number']
                numbers = sorted(result['predicted_numbers'])
                match_count = result['match_count']
                rank = result['rank']
                prize = result['prize']
                source = result['source']
                confidence = result['confidence']
                
                rank_emoji = {1: "🏆", 2: "🥈", 3: "🥉", 4: "⭐", 5: "✅"}
                report.append(f"{rank_emoji.get(rank, '')} [{set_num}세트] {numbers}")
                report.append(f"   → {match_count}개 일치, {rank}등 당첨! 💰 {prize:,}원")
                report.append(f"   → 출처: {source} (신뢰도: {confidence:.1%})")
                report.append("")
        
        # 통계 요약
        report.append("-" * 60)
        report.append("📈 통계 요약")
        report.append("-" * 60)
        
        total_wins = sum(rank_distribution.values())
        win_rate = (total_wins / len(results)) * 100 if results else 0
        avg_matches = sum(r['match_count'] for r in results) / len(results)
        
        report.append(f"• 당첨률: {total_wins}/{len(results)}세트 ({win_rate:.1f}%)")
        report.append(f"• 평균 일치 개수: {avg_matches:.2f}개")
        
        if total_wins > 0:
            report.append(f"• 총 예상 당첨금: {total_prize:,}원")
            report.append("")
            report.append("• 등수별 분포:")
            for rank in range(1, 6):
                if rank_distribution[rank] > 0:
                    report.append(f"  {rank}등: {rank_distribution[rank]}세트")
        
        report.append("")
        report.append("• 일치 개수 분포:")
        for match in range(7):
            if match_distribution[match] > 0:
                percentage = (match_distribution[match] / len(results)) * 100
                bar = "█" * int(percentage / 2)  # 막대 그래프
                report.append(f"  {match}개: {match_distribution[match]:3d}세트 ({percentage:5.1f}%) {bar}")
        
        # 소스별 성과
        source_stats = {}
        for result in results:
            source = result['source']
            if source not in source_stats:
                source_stats[source] = {'total': 0, 'wins': 0, 'matches': 0}
            source_stats[source]['total'] += 1
            source_stats[source]['matches'] += result['match_count']
            if result['rank'] > 0:
                source_stats[source]['wins'] += 1
        
        if len(source_stats) > 1:
            report.append("")
            report.append("• 예측 소스별 성과:")
            for source, stats in sorted(source_stats.items(), 
                                       key=lambda x: x[1]['matches']/x[1]['total'], 
                                       reverse=True):
                avg_match = stats['matches'] / stats['total']
                win_rate = (stats['wins'] / stats['total']) * 100
                report.append(f"  {source}: 평균 {avg_match:.2f}개 일치, "
                            f"{stats['wins']}/{stats['total']}세트 당첨 ({win_rate:.1f}%)")
        
        report.append("=" * 60)
        
        return "\n".join(report)
    
    def generate_report(self, round_num: int, actual_numbers: List[int],
                        bonus_number: int, results: List[Dict],
                        rank_counts: Dict, total_prize: int) -> str:
        """
        결과 보고서 생성
        
        Returns:
            포맷된 보고서 문자열
        """
        report = []
        report.append("=" * 52)
        report.append(f"📊 예측 결과 확인 - {round_num}회차")
        report.append("=" * 52)
        report.append(f"실제 당첨번호: {sorted(actual_numbers)} + 보너스 [{bonus_number}]")
        report.append("")
        
        # 각 세트별 결과
        for result in results:
            set_num = result['set_number']
            numbers = sorted(result['predicted_numbers'])
            match_count = result['match_count']
            rank = result['rank']
            prize = result['prize']
            
            report.append(f"[예측 {set_num}세트] {numbers}")
            
            if rank > 0:
                rank_emoji = {1: "🏆", 2: "🥈", 3: "🥉", 4: "⭐", 5: "✅"}
                report.append(f"  {rank_emoji.get(rank, '')} {match_count}개 일치 → {rank}등 당첨! 💰 {prize:,}원")
            else:
                report.append(f"  ❌ {match_count}개 일치 → 미당첨")
            report.append("")
        
        # 전체 성과
        report.append("-" * 52)
        report.append("📈 이번 회차 성과")
        
        total_wins = sum(rank_counts.values())
        win_rate = (total_wins / 5) * 100 if total_wins > 0 else 0
        
        report.append(f"- 총 5세트 중 {total_wins}세트 당첨 ({win_rate:.0f}% 적중률)")
        
        if total_wins > 0:
            best_rank = min([r for r, c in rank_counts.items() if c > 0])
            report.append(f"- 최고 등수: {best_rank}등")
            report.append(f"- 총 당첨금: {total_prize:,}원")
        
        # 평균 일치 개수
        avg_matches = sum(r['match_count'] for r in results) / len(results)
        report.append(f"- 평균 일치 개수: {avg_matches:.1f}개")
        
        # 누적 성과
        performance = self.prediction_tracker.get_performance_summary()
        if performance['total_rounds'] > 0:
            report.append("")
            report.append(f"📊 누적 성과 (최근 {performance['total_rounds']}회)")
            report.append(f"- 총 {performance['total_predictions']}세트 중 {performance['total_wins']}세트 당첨")
            report.append(f"- 누적 당첨금: {performance['total_prize']:,}원")
            report.append(f"- 평균 정확도: {performance['avg_accuracy']:.2f}개")
        
        report.append("=" * 52)
        
        return "\n".join(report)