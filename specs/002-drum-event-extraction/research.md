# Research: Drum Event Extraction (PoC 2)

**Date**: 2026-10-04
**Inputs**: [spec.md](spec.md), [docs/poc-plan.md](../../docs/poc-plan.md) (ADTOF-pytorch は承認済み)、
ADTOF-pytorch のソースコード (`xavriley/ADTOF-pytorch` コミット `85c192e`, 2025-11-11)、PyPI / GitHub の現在の情報、
Roland TD-17 のサポート情報

---

## R-01: 打撃イベントの推定方式

- **Decision**: ADTOF-pytorch をコミット `85c192e78f716ea0b111cc8a5ee4a8f6a3a4f8a9` に固定して git から入れる。
  同梱の `transcribe_to_midi` は使わず、下位の関数 (`create_frame_rnn_model` / `load_pytorch_weights` / `load_audio_for_model` /
  `NotePeakPickingProcessor`) を adapter (`poc/transcription/adtof_adapter.py`) から呼ぶ。
- **Rationale**:
  - 依存は torch / librosa / pretty_midi / numpy のみで、TensorFlow や madmom が不要 (poc-plan §3.2 で選定済み)。
  - 重みは約 3.6 MB とごく小さく、モバイル化に有利。
  - `transcribe_to_midi` は MIDI ファイルしか返さず、打撃の強さ (活性値) も捨てる。下位の関数を使えば、活性値から強さを取り出し、Domain Model (DrumEvent) に変換できる (Constitution III)。
  - `transcribe_to_midi` は `device` に `cuda` / `cpu` しか受け付けない。下位の関数なら自分でデバイスを選べる。
- **確認した仕様** (ソースコードより):
  - 出力クラスは 5 つ: `LABELS_5 = [35 (Kick), 38 (Snare), 47 (Tom), 42 (HiHat), 49 (Cymbal)]`、既定の閾値 `[0.22, 0.24, 0.32, 0.22, 0.30]`
  - 入力は 44.1 kHz モノラルに変換し、最大値で正規化。STFT (n_fft 2048, hop 441 = 100 fps, `center=True`)。フレーム `i` は時刻 `i / 100` 秒を中心とするため、時刻の基準はずれない
  - モデルは CNN + 双方向 GRU (曲全体を一度に処理するオフライン方式)
  - ピーク検出は移動平均を引いたうえで局所最大を取り、20 ms 以内の近いピークをまとめる (`combine = 0.02`)
- **時間分解能**: 1 フレーム = 10 ms。量子化による誤差は ±5 ms 以内で、SC-002 (中央値 10 ms 以下) には収まる見込み。
  未達の場合は、活性値のピークを 2 次関数で補間して 10 ms 未満の時刻を推定する方法を追加する (今回は入れない)。
- **Alternatives considered**: ADTOF オリジナル (TensorFlow + madmom が必要で、madmom は Python 3.10+ で PyPI から入らない)、
  ADTOF Plus (追加で約 500 MB の分離モデルと AGPL の essentia が必要)、Omnizart (精度が低い世代)。いずれも poc-plan §3.2 で検討済み。

## R-02: 打撃の強さ (FR-002, FR-016)

- **Decision**: ピークのフレームでの活性値 (0〜1) をそのまま強さとする。
- **Rationale**: 追加の処理なしで得られ、強く叩いた打撃ほど活性値が高くなる傾向がある。MIDI の velocity との順位相関 (Spearman) で一致度を記録する (合否には使わない)。
- **Alternatives considered**: Drum Stem の音量から推定する (楽器が重なると分けられない)。

## R-03: 実行デバイス

- **Decision**: CPU で実行する。
- **Rationale**: モデルが小さく (3.6 MB)、4 分の曲でも 24,000 フレーム程度のため CPU で十分速い見込み (SC-004 の 2 分を大きく下回るはず。初回実行で計測する)。
  CPU なら同じ入力で同じ結果になりやすい (SC-005)。MPS は必要になったときに検討する。

## R-04: 依存関係と Python バージョン

- **Decision**: Python 3.11 のまま、以下を追加する。`uv pip compile` で解決できることを確認済み。

  | パッケージ | 解決されたバージョン | 用途 | 承認 |
  |---|---|---|---|
  | adtof-pytorch (git, `85c192e`) | 0.1.0 | 打撃イベントの推定 | poc-plan で承認済み |
  | librosa | 0.11.0 | ADTOF-pytorch の依存 (音声読み込み・STFT) | poc-plan で承認済み |
  | pretty_midi | 0.2.11.post0 | 確認用 MIDI の出力 | poc-plan で承認済み |
  | scipy | 1.17.1 | 1 対 1 の対応付け、順位相関 (librosa 経由で入る。直接使うので明記) | 実質追加なし |
  | **sounddevice** | 0.5.6 (MIT, 2026-08 更新) | TD-17 での伴奏の再生と音声の録音 | **新規 — Human Review が必要** |
  | **python-rtmidi** | 1.5.8 (MIT 系, 2023-11 リリース, GitHub は 2026-01 更新) | TD-17 からの MIDI の受信 | **新規 — Human Review が必要** |

- **注意**: librosa 1.0 と scipy 1.18 は Python 3.12 以上が必要。Python 3.11 では librosa 0.11 / scipy 1.17 になる。
  Python を 3.12 に上げるかは PoC 2 では検討しない (Demucs・Beat This! の対応を含めて PoC 3 以降で判断する)。
- **Alternatives considered**: DAW (GarageBand / Logic) で録音して書き出す (MIDI の書き出しや時刻合わせが手作業になり、再現性が下がる)。

## R-05: TD-17 での録音方法 (Clarifications: TD-17 の USB で MIDI と音声を同時録音)

- **Decision**: `poc record` コマンドを作り、1 つのコマンドで次を行う。
  1. sounddevice で TD-17 (USB オーディオ) に対して **入出力を 1 つのストリーム (duplex)** で開く
  2. 伴奏 (PoC 1 の `accompaniment.wav`) を TD-17 に送って再生する。開発者は TD-17 のヘッドホン端子で、伴奏と自分のドラムを一緒に聴く
  3. 同じストリームで TD-17 の USB 音声 (ドラムの音) を録音する
  4. python-rtmidi で TD-17 の MIDI を受け取り、受信時刻を記録する
- **Rationale**:
  - 再生と録音が同じストリーム (同じクロック) なので、録ったドラムの音と伴奏の時間関係を、ストリームの遅延 (入力 + 出力) で正確に戻せる。評価用の曲を作るときに、ドラムを伴奏の時間軸に揃えられる。
  - ケーブルは USB 1 本で済む。
- **前提**: Roland 公式ドライバ (TD-17 Driver Ver.1.0.3, macOS Sonoma 14 以降) を開発者が入れ、TD-17 の `SETUP → USB → USB Driver Mode` を `VENDOR` にする。macOS 15 での動作は Step 0 で確認する。

## R-06: MIDI と音声の時刻合わせ (FR-006a, SC-008)

- **Decision**:
  - MIDI の受信時刻と録音開始の時刻は `time.perf_counter()` で同じ時計に揃える (粗い合わせ)。
  - 細かい合わせは録音した音から行う。録音はドラムだけなので、音の立ち上がり (オンセット) がはっきりしている。MIDI の各ノートから ±30 ms 以内で最も近いオンセットを探し、ずれの**中央値**を補正値とする。
  - 補正後の、打撃ごとのずれの標準偏差を記録する (SC-008: 1 ms 以下)。対応が取れたノートが 80% 未満、または標準偏差が 1 ms を超えたら警告を出し、評価を止める (spec のエッジケース)。
- **Rationale**: TD-17 の MIDI と音声は同じモジュールから出るため、ずれはほぼ一定。MIDI の受信時刻には OS の揺らぎがあるが、中央値を使えば外れ値に強い。
- **オンセットの検出**: スペクトルの変化量 (spectral flux) のピークを、サンプル単位で立ち上がり位置に絞り込む。librosa の onset 関数で十分 (新しい依存なし)。

## R-07: 伴奏が録音に混ざらないことの確認 (spec Assumptions)

- **Decision**: `poc record --check` で、伴奏を 5 秒流しながら何も叩かずに録音し、録った音の RMS と、伴奏との相関を測る。
  録った音が無音に近く (RMS が伴奏より 40 dB 以上小さい)、伴奏との相関がなければ OK。混ざっていたら、TD-17 の USB の設定 (オーディオのループバックなど) を見直す。
- **あわせて確認すること**: 各パッドを叩いたときに届く MIDI ノート番号を表示し、R-08 の対応表と合っているかを確かめる。

## R-08: TD-17 の MIDI ノート番号と楽器の対応 (FR-006)

- **Decision**: 既定の対応表を `poc/recording/td17_note_map.yaml` に置き、`poc record --check` で実機に合わせて確認・変更できるようにする。

  | 楽器 (評価) | TD-17 の既定のノート番号 |
  |---|---|
  | kick | 36 |
  | snare | 38 (ヘッド), 40 (リム), 37 (クロススティック) |
  | hihat | 42 (クローズ・ボウ), 22 (クローズ・エッジ), 46 (オープン・ボウ), 26 (オープン・エッジ), 44 (ペダルの「チッ」) |
  | 対象外 (tom / cymbal) | 48, 50, 45, 47, 43, 58 (タム) / 49, 55, 57, 52, 51, 59, 53 (シンバル) |

  ペダルの開き具合 (CC #4) などのノート以外のメッセージは無視する (spec のエッジケース)。
- **Rationale**: Roland V-Drums の一般的な既定値。キットごとに変更できるため、実機で確認する。

## R-09: ゴーストノートの判定 (FR-009)

- **Decision**: MIDI の velocity が **40 未満** の Snare・HiHat をゴーストノートとする (Kick には適用しない)。閾値は設定で変えられる。
- **Rationale**: TD-17 の velocity は 1〜127。一般的な演奏ではゴーストノートは 20〜40 程度になることが多い。実際の録音の velocity の分布を見て、必要なら閾値を見直す。

## R-10: 評価用の曲の作り方 (FR-006a)

- **Decision**:
  1. 録ったドラムの音を、ストリームの遅延分だけ前にずらして伴奏の時間軸に揃える (R-05)
  2. ドラムの音量を、原曲で PoC 1 が測った Drum Stem の音量比 (`run.json` の `rms_db_relative_to_mix`) と同じになるように調整する
  3. 伴奏と足して 44.1 kHz ステレオの WAV にする (クリップしないよう float32)
  4. 正解データの時刻も同じだけずらす
- **Rationale**: 原曲と同じくらいのドラムの大きさにすることで、分離・抽出の難しさを原曲に近づける。

## R-11: 正解との対応付け (FR-007)

- **Decision**: 楽器ごとに、正解と推定の組のうち時刻差が許容範囲 (±50 ms) 以内のものだけを候補にし、`scipy.optimize.linear_sum_assignment` で**対応数が最大かつ時刻差の合計が最小**になる 1 対 1 の組を求める。
- **Rationale**: 単純に「一番近い推定」を選ぶと、1 つの推定が 2 つの正解に使われたり、連打で取り違えたりする (Constitution / CLAUDE.md の Performance Analysis の方針)。
- **指標**: TP / FN / FP、Precision / Recall / F1、TP のずれ (推定 − 正解) の平均絶対誤差・中央値・95 パーセンタイル (ms)。符号付きの中央値も記録する (推定が全体に早い・遅いかを見るため)。

## R-12: 伴奏に残った元のドラムの影響 (FR-015)

- **Decision**: PoC 1 の `accompaniment.wav` をそのまま (分離せずに) 推定にかけ、評価区間内で検出された打撃の数を楽器ごとに数えて評価結果に併記する。
- **Rationale**: 評価用の曲を分離したとき、伴奏に残った元のドラムは Drum Stem 側に入る。伴奏単体での検出数は、その影響の目安になる。

## R-13: 手動アノテーション (FR-006b)

- **Decision**: 外部ツール (例: Sonic Visualiser。リポジトリの依存にはしない) で打撃に印を付け、CSV で書き出す。
  形式: `annotation.yaml` (対象の PoC 1 の run_id、確認区間の開始・終了) と `hits.csv` (`time_sec,label`)。
  ラベルは `k` / `s` / `h`、ゴーストノートは末尾に `g` (例: `sg`)。
- **Rationale**: Sonic Visualiser は時刻とラベルの CSV を書き出せる。ラベルを短くすると打ち込みが速い。

## R-14: 確認用の出力 (FR-005)

- **Decision**:
  - WAV: 原曲 (PoC 1 の入力) に、打撃の位置でウッドブロックのような短い音 (基音 + 2.76 倍の倍音、減衰 12 ms、長さ 60 ms。Kick 400 Hz / Snare 800 Hz / HiHat 1.6 kHz、強さで音量を変える) を重ねる。Tom・Cymbal は鳴らさない。
    (2026-10-04 開発者の試聴を受けて、サイン波のクリックからドラムと聴き分けやすいウッドブロック系の音に変更)
  - MIDI: pretty_midi で General MIDI のドラム (Kick 36 / Snare 38 / HiHat 42 / Tom 47 / Cymbal 49)、velocity = 強さ × 127
- **Rationale**: 木の打楽器のような音はドラムの音色と混ざりにくく、サイン波より耳に優しい。400 Hz 以上ならノート PC のスピーカーでも聴こえる。

## R-15: 実行記録・再現性 (FR-011, SC-005, SC-006)

- **Decision**: PoC 1 の `run.json` と同じ考え方で `transcription.json` を出す (入力 = PoC 1 の run_id と音声の sha256、方式・バージョン・コミット、閾値、処理時間、最大メモリ、環境、警告)。
  計測には PoC 1 の `poc/evaluation/metrics.py` を使う。SC-005 は同じ入力で 2 回実行してイベント一覧が一致するかで確認する。

## R-16: 検出の閾値の調整 (2026-10-04 追加)

- **きっかけ**: US1 の試聴 (T015) で、開発者が「速い 8 ビートで HiHat が所々抜ける」「Kick の 8 分 2 連 (ドド) が 1 発になる」と指摘した。
  B・BLUE の Drum Stem で活性値を調べると、検出された打撃の 100〜250 ms 後に閾値 (0.22) に届かない山が Kick で 30 個、HiHat で 123 個あった
  (HiHat はそのうち 51 個が 0.15〜0.22)。Kick・HiHat の閾値を 0.12 に下げると、Kick +14 (507 → 521)、HiHat +104 (602 → 706) になり、
  開発者の試聴では「下げたほうがいい感じ」だった。
- **Decision**:
  - `poc transcribe` に `--thresholds` オプションを追加し、楽器ごとに閾値を変えられるようにする (FR-012 の差し替え・比較の範囲内)。
  - 既定値は ADTOF の元の閾値のまま残し、比較の基準点とする。
  - 最終的な閾値は、US2 の正解データ (TD-17) を使って楽器ごとに探索して決める (`poc tune-thresholds`)。
    同じ 5 曲で閾値を選んで評価すると結果が甘くなるため、**1 曲を除いた 4 曲で選び、除いた 1 曲で評価する (leave-one-out)** を 5 回行い、その平均を SC-001 の判定に使う。
- **Rationale**: 耳だけで閾値を下げると、余計な検出 (FP) の増加を見落とす。正解データがあれば Precision と Recall の釣り合いを数字で決められる。
- **探索の実装**: 推定 (モデルの推論) は 1 回だけ行い、活性値を保存して、閾値ごとにピーク検出だけをやり直す (推論の数秒 × 閾値の数にならないようにする)。
