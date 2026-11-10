# JBNU 소프트웨어아키텍처설계 과제3 — 마이크로커널 아키텍처 스타일을 적용한 시스템 구현

202110914 김대진

- 제출 보고서: [`과제3-보고서.pdf`](과제3-보고서.pdf) — 진행 과정, 시스템 화면, 구조, 코어와 서버의 인터랙션, 품질 문제와 해결, 검증, 사용한 프롬프트
- 사용한 프롬프트: [`prompt.md`](prompt.md)

## 낸 시스템

`candidate-docconv/` — 문서 → Markdown 변환기. txt·html·docx·hwpx·pdf 를 Markdown 으로 바꾸는 로컬 웹 앱입니다. 형식별 변환기와 후처리기가 플러그인이고, 서버를 끄지 않고 플러그인을 설치·제거합니다.

```bash
cd candidate-docconv
python tools/make_samples.py     # samples/ 에 시연 자료 생성
python app.py                    # http://127.0.0.1:8802
python -B -m unittest discover -s tests
```

Python 3.14 표준 라이브러리만 씁니다. pdf 변환기만 PyMuPDF 를 씁니다. 자세한 사용법과 5분 시연 절차는 `candidate-docconv/README.md` 에 있습니다.

## 폴더

| 경로 | 내용 |
|---|---|
| `report.html`, `과제3-보고서.pdf` | 보고서(HTML 원본과 제출용 PDF) |
| `capture/` | 보고서에 넣은 화면 캡처 |
| `candidate-docconv/` | 낸 시스템(후보 B) |
| `candidate-auction/` | 비교용 후보 A 온라인 경매. 구현 검토 지적 10건을 고치지 않은 상태입니다(보고서 1.4) |
| `지시서/` | 구현 지시서(공통·A·B)와 교차 검토 13회 기록 |
| `prompt.md` | 과제를 진행하며 한 지시를 순서대로 적은 기록(보고서 부록 A) |
| `과제2-회고.md` | 과제2 진행에서 부족했던 점과 이번에 바꾼 것 |

보고서 HTML 을 고치면 PDF 도 다시 만듭니다.
