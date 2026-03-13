.. 로또 예측 시스템 documentation master file

로또 예측 시스템 문서
=====================

ML/AI를 활용한 로또 번호 분석 및 예측 시스템입니다.

.. toctree::
   :maxdepth: 2
   :caption: 시작하기:

   ARCHITECTURE
   main_execution_guide

.. toctree::
   :maxdepth: 2
   :caption: API 레퍼런스:

   api/core
   api/filters
   api/ml

.. toctree::
   :maxdepth: 2
   :caption: 가이드:

   ADAPTIVE_FILTER_GUIDE
   threshold_manager_guide
   SYSTEM_PHILOSOPHY

.. toctree::
   :maxdepth: 1
   :caption: 성능 및 분석:

   PERFORMANCE_METRICS_QUICK_REF
   FILTER_METRICS_QUICK_REF


시스템 개요
-----------

로또 예측 시스템은 다음과 같은 핵심 구성요소로 이루어져 있습니다:

1. **데이터 수집**: 동행복권에서 당첨번호 자동 수집
2. **필터링 시스템**: 16개 통계 필터로 조합 축소 (8.14M → ~300K)
3. **ML/AI 예측**: LSTM, Ensemble, Monte Carlo 모델
4. **자동 최적화**: Optuna 기반 임계값 최적화

빠른 시작
---------

.. code-block:: bash

   # 전체 시스템 실행
   python main.py

   # 테스트 실행
   python -m pytest tests/


인덱스
------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
