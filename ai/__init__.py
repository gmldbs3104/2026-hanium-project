"""
AI 모듈 최상위 패키지.

백엔드(backend/app/services/ai_adapters.py)가 `ai.detection...`, `ai.canvas...`
형태로 import할 수 있도록 ai/ 디렉토리를 패키지로 만든다.

의도적으로 아무것도 eager-import하지 않는다 — `ai.detection`은 torch/CRAFT를
로드하므로(무겁고 GPU/모델 파일 의존), 캔버스 모드처럼 torch가 필요 없는
경로에서 `import ai.canvas.stroke_grouping`만으로 가볍게 쓸 수 있어야 한다.
필요한 쪽에서 서브모듈을 직접 import할 것:

    from ai.preprocessing.image_preprocessor import ImagePreprocessor
    from ai.detection.craft_detector import craft_detect_chars      # torch 로드됨
    from ai.analysis.handwriting_analyzer import analyze_size_angle
    from ai.canvas.stroke_grouping import group_strokes_into_chars
    from ai.canvas.canvas_quality_analyzer import analyze_canvas_writing
"""
