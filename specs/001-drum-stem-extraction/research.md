# Research: Drum Stem Extraction (PoC 1)

**Date**: 2026-10-03
**Inputs**: [spec.md](spec.md), [docs/poc-plan.md](../../docs/poc-plan.md) (承認済みの技術選定), Demucs v4.1.0 のソースコード
(`adefossez/demucs`: `demucs/api.py`, `demucs/apply.py`, `demucs/audio.py`, `demucs/separate.py`)

技術選定 (Demucs v4 `htdemucs`、Python 3.11、ffmpeg) は `docs/poc-plan.md` で承認済みのため、ここでは PoC 1 の実装上の未決事項を扱う。

---

## R-01: 分離の呼び出し方

- **Decision**: Demucs の Python API `demucs.api.Separator` の `separate_tensor(wav, sr)` を使う。音声の読み込みと書き出しは自前で行う。
- **Rationale**: `separate_audio_file` や CLI は Demucs 側でデコード・保存を行うため、DRM 判定・サンプルレート・クリップ処理・実行記録を制御できない。
  `separate_tensor` は float32 の `(channels, samples)` テンソルを受け取り、stem 名 → テンソルの dict を返すため、adapter として閉じ込めやすい (Constitution III)。
- **Alternatives considered**: CLI をサブプロセスで呼ぶ (出力パス・クリップ処理を制御できない)、`apply_model` を直接呼ぶ (正規化処理を自前で再実装する必要がある)。

## R-02: 再現性 (SC-006) とランダム性

- **Decision**: `shifts=0` に固定する。加えて `random` / `numpy` / `torch` のシードを固定し、実行記録に保存する。
- **Rationale**: `Separator` の既定値は `shifts=1` で、`apply.py` は `random.randint(0, 0.5 秒)` のランダムな時間シフトを入れてから元に戻す実装になっている。
  `shifts=0` ならランダムな処理は入らない。`shifts` を増やすと品質は少し上がるが処理時間は比例して増え、PoC の判断には不要。
- **Alternatives considered**: `shifts=1` のままシードだけ固定する (Demucs 内部の `random` 利用に依存して壊れやすい)。
- **許容差**: MPS (GPU) では浮動小数点演算の順序が実行ごとに変わり得るため、SC-006 の判定は「2 回の実行で Drum Stem のサンプルごとの最大絶対差 ≤ 1e-4」とする。CPU 実行では完全一致を期待する。

## R-03: 実行デバイス (M1)

- **Decision**: MPS が使えれば MPS、使えなければ CPU。`--device` で明示的に指定もできる。使ったデバイスは実行記録に残す。
- **Rationale**: Demucs の `separate.py` は CUDA → MPS → CPU の順で自動選択しており、MPS での動作が想定されている。
  README によると CPU では曲長の約 1.5 倍の時間がかかる (4 分の曲で約 6 分)。CPU でも SC-005 (10 分以内) を満たす見込みのため、MPS で問題が出たら CPU に切り替える。
- **Alternatives considered**: CPU 固定 (遅いが確実。MPS で問題があった場合の退避先として残す)。

## R-04: 音声のデコード・入力形式

- **Decision**: すべての入力を ffmpeg (サブプロセス) で **元のサンプルレート・元のチャンネル数のまま** float32 PCM にデコードし、numpy 配列で受け取る。メタ情報は ffprobe (JSON 出力) で取得する。
- **Rationale**: WAV / AIFF / MP3 / AAC / ALAC を 1 つの経路で扱える。Demucs v4.1.0 は内部で sphn + ffmpeg を使うが、そこを通さずに自前でデコードすれば、サンプルレート変換を自分で制御できる。
- **MP3 / AAC のエンコーダ遅延**: ffmpeg は MP3 (LAME / Xing ヘッダ) と AAC (iTunSMPB / edit list) のエンコーダ遅延 (priming samples) を既定で取り除くため、デコード結果は元の曲の時間軸に揃う。PoC では、デコード結果の長さを ffprobe の duration と比べ、差が 1 ms を超えたら警告する。
- **Alternatives considered**: soundfile / libsndfile (MP3 は読めるが AAC / ALAC は読めない)、librosa (内部で audioread / soundfile を使い、挙動の制御が難しい)。

## R-05: DRM 保護ファイルの判定 (FR-005)

- **Decision**: 以下のいずれかに当てはまれば DRM 保護ファイルとして扱い、デコード前に拒否する。
  1. 拡張子が `.m4p` (FairPlay 保護の AAC)
  2. ffprobe で得たオーディオストリームの `codec_tag_string` が `drms` (FairPlay の暗号化サンプルエントリ)
  3. ffprobe / ffmpeg のエラーメッセージに DRM 関連の語 (`drm`, `encrypted`, `protected`) が含まれる
- **Rationale**: Apple の保護ファイルは `drms` というサンプルエントリで識別できる。復号は一切試みない (Constitution IV)。
- **Alternatives considered**: デコードを試して失敗したら拒否する (失敗の原因が DRM かどうか区別できず、メッセージが曖昧になる)。
- **確認方法**: 保護ファイルの実物はリポジトリに置かない。判定ロジックは ffprobe の JSON 出力をテスト用に用意して単体テストする。手元に保護ファイルがあれば手動で確認する。

## R-06: サンプルレートと時間軸 (FR-003, SC-004)

- **Decision**: 原曲が 44.1kHz 以外の場合、`julius.resample_frac` で 44.1kHz に変換して分離し、出力 stem を同じ方法で原曲のサンプルレートに戻す。最後に、原曲とサンプル数がぴったり同じになるよう末尾を切り詰め / ゼロ埋めする。
- **Rationale**: 出力 stem のサンプルレートとサンプル数を原曲と揃えておけば、後の PoC で「時刻 = サンプル番号 / SR」を原曲・stem 共通で使える。julius のリサンプルは左右対称の sinc フィルタを使うため、時間方向のずれは生じない (Demucs 内部の変換と同じ実装)。
- **Alternatives considered**: stem を 44.1kHz のまま保存して、時刻を秒で扱う (原曲とサンプル数が一致せず、SC-004 の検証と後続処理が煩雑になる)。

## R-07: 時間ずれ 1 ms 以下の検証方法 (SC-004)

- **Decision**: 分離後に、**全 stem の和** (drums + bass + other + vocals) と原曲を、それぞれモノラルにした上で相互相関を取る。相関がピークになる位置 (lag) を ms に換算して実行記録に残す。判定は |lag| ≤ 1 ms。
  計算量を抑えるため、RMS が最も大きい 30 秒の区間を使い、numpy の FFT で計算する。
- **Rationale**: Demucs の各 stem の和はおおよそ元のミックスに戻るため、正解トラックがなくても時間方向のずれを測れる。あわせて、原曲と stem のサンプル数が一致していることも記録する。
- **Alternatives considered**: Drum Stem と原曲を直接比べる (ドラム以外の成分が混ざって相関が鈍くなる)、聴感で確認するだけ (1 ms の精度は耳では判断できない)。

## R-08: 出力形式・クリップ (FR-004, Edge Case)

- **Decision**: stem は **32-bit float WAV** で `soundfile` を使って書き出す。音量の加工はしない。ピークの絶対値が 1.0 を超えた場合は、実行記録に `clipping_risk` の警告を残す。
- **Rationale**: Demucs の `save_audio` は既定値 (`clip='rescale'`) で stem の音量を自動的に縮めるため、そのまま使うと原曲との音量関係が崩れる。float32 なら 1.0 を超える値もそのまま保持できるので、PoC 2 の打撃強度の推定で歪みが出ない。
- **Alternatives considered**: 16-bit / 24-bit PCM (1.0 を超える値がクリップされ、音量関係を保つにはリスケールが必要)。

## R-09: 伴奏 stem (FR-013)

- **Decision**: Accompaniment = bass + other + vocals の和。drums と同じ形式で保存する。
- **Rationale**: Demucs は 4 stem を一度に出力するため、追加の処理はほぼかからない。

## R-10: 「ドラム成分がほとんど検出されない」の判定 (Edge Case)

- **Decision**: Drum Stem の RMS が原曲の RMS より 30 dB 以上小さい場合、警告 `drums_nearly_silent` を残す (出力はそのまま保存する)。
- **Rationale**: 曲の中でドラムが鳴っている区間が少なくても、全体の RMS 比で大まかに判定できる。閾値は評価結果を見て変えてよい (実行記録に閾値を残す)。

## R-11: 実行記録・メモリ計測 (FR-010)

- **Decision**:
  - 入力の識別情報: ファイル内容の SHA-256
  - 処理時間: `time.perf_counter()` で、デコード・分離・保存の段ごとと合計を記録
  - 最大メモリ: `resource.getrusage(RUSAGE_SELF).ru_maxrss` (macOS ではバイト単位)。MPS を使った場合は `torch.mps.driver_allocated_memory()` の最大値も別項目として記録する
  - バージョン: Python / torch / demucs (`importlib.metadata`)、モデル名、ffmpeg のバージョン文字列
- **Rationale**: 標準ライブラリと torch の機能だけで計測できる。M1 はユニファイドメモリのため、GPU 側に確保されたメモリは RSS に正しく出ない可能性があり、両方を残す。
- **Alternatives considered**: psutil (依存が増える。ru_maxrss で十分)、memory_profiler (計測の負荷が大きい)。

## R-12: 出力の保存場所と原子性 (FR-007, FR-014, Edge Case)

- **Decision**: 1 回の実行ごとに `output/runs/<YYYYMMDD-HHMMSS>_<sha256 先頭 8 文字>/` を作る。処理中は `<run_id>.partial/` に書き、成功したらリネームする。失敗したら `.partial` を削除する。
- **Rationale**: 実行ごとにディレクトリを分けるので上書きが起きない。リネームは同じファイルシステム内では原子的に行われるため、不完全な出力が残らない。`output/` は `.gitignore` 済み。

## R-13: 聴感評価の記録 (FR-008, FR-009, FR-011)

- **Decision**: 実行ごとに評価シートの YAML テンプレートを生成し、開発者が `verdict` (ok / ng) と `issues` (気になった楽器・問題) をエディタで記入する。曲名はファイル名から自動で記入する。集計コマンドですべての評価シートを読み込み、曲ごとの CSV と全体の集計 (Markdown) を出力する。
- **Rationale**: PoC 1 で知りたいのは「PoC 2 に進めるか」だけであり、打撃の検出精度は PoC 2 で正解データを作って定量評価する。PoC 1 で打撃を手で数えると PoC 2 と同じ作業の重複になるため、1 曲あたり数分で終わる OK / NG 判定にした (2026-10-04 の spec 変更)。
  PyYAML は Demucs の依存として既に入るため、新しい依存は増えない (直接 import するので `pyproject.toml` には明記する)。
- **Alternatives considered**: 確認区間 (4 小節 × 3) の打撃数と 5 段階評価 (当初案。作業が重く PoC 2 と重複するため廃止)、CSV (自由記述のメモを書きにくい)、専用の UI (PoC の範囲外。Constitution V)。

## R-14: テスト方針

- **Decision**:
  - 単体テスト: 合成した信号 (サイン波・クリック列) とモックの ffprobe 出力を使い、デコード・DRM 判定・リサンプルとサンプル数合わせ・相互相関による lag 計算・警告判定・評価シートの集計を検証する
  - パイプラインのテスト: 分離部分を `FakeSeparator` (入力をそのまま drums として返すなど) に差し替えて、実行記録と原子的な保存を検証する
  - 統合テスト (`@pytest.mark.slow`): 合成したクリック音源で実際に Demucs を動かし、出力の長さと lag ≤ 1 ms を確認する。モデルのダウンロードが必要なため、既定では実行しない
- **Rationale**: 著作物をテストに使わない (Constitution IV)。分離モデルを差し替えられる構造 (FR-012) を、テストで実際に差し替えて確認できる。
