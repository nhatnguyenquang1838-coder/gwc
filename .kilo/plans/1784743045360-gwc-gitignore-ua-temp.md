# Plan — Tách nhánh + cập nhật `.gitignore` cho UA temp artifacts

## Goal
Ngăn các file/thư mục runtime của Understand Anything bị git theo dõi hoặc leak, bằng cách tạo nhánh chuyên biệt và sửa `.gitignore` phù hợp.

## Context
- Các artifact UA hiện có trong repo: `.ua/intermediate/batches.json`, `.ua/intermediate/scan-result.json`, `.ua/tmp/*`, `.ua/.understandignore`, `.ua/fingerprints.json`, `.ua/meta.json`, `.ua/knowledge-graph.json`
- Trong đó `.ua/knowledge-graph.json`, `.ua/meta.json`, `.ua/fingerprints.json`, `.ua/.understandignore` là các artifact cốt lõi dùng cho staleness detection, incremental analysis, theme loading, và graph build configuration.
- Nhiều file UA mới đang ở trạng thái untracked, đặc biệt `.ua/tmp/` đang mở trong session.

## Decisions
- **Nhánh mới**: `chore/gitignore-ua-temp`
- **Giữ lại trong git, không ignore**:
  - `.ua/knowledge-graph.json` — artifact chính, được yêu cầu MUST keep
  - `.ua/.understandignore` — cấu hình ignore của UA, ảnh hưởng đến graph build
  - `.ua/meta.json` — metadata bắt buộc: lưu `gitCommitHash` cho staleness detection, theme fallback cho dashboard, và là prerequisite trước khi ghi fingerprint baseline
  - `.ua/fingerprints.json` — baseline fingerprint per-file dùng cho incremental analysis; nếu thiếu, mọi commit sẽ bị phân loại là `STRUCTURAL` và trigger `FULL_UPDATE` mãi mãi
- **Thêm vào `.gitignore`**:
  - `.ua/tmp/`
  - `.ua/intermediate/`
- **Tracked cleanup mode**: `git rm --cached --dry-run` trước để xác nhận danh sách, rồi mới xóa thật chỉ các file UA đã quyết định ignore nhưng đang tracked. Không dùng `git rm -r` nếu không cần.

## Tasks
1. Tạo nhánh từ `main`: `git switch -c chore/gitignore-ua-temp`
2. Thêm vào `.gitignore`:
   - `.ua/tmp/`
   - `.ua/intermediate/`
3. Xác minh danh sách file UA đang được track cần hủy tracking: `git ls-files .ua`
4. Hủy tracking có chọn lọc: `git rm --cached` các file UA đã quyết định ignore nhưng đang tracked, **KHÔNG** bao gồm `.ua/knowledge-graph.json`, `.ua/.understandignore`, `.ua/meta.json`, `.ua/fingerprints.json`
5. Commit: `chore: ignore UA temp/runtime artifacts` chỉ chứa thay đổi `.gitignore` và `git rm --cached` liên quan UA
6. Push nhánh: `git push -u origin chore/gitignore-ua-temp`
7. Tạo Draft PR về `main`

## Risques / khuyến nghị
- `.ua/meta.json` và `.ua/fingerprints.json` là dependency của UA incremental update flow. Việc ignore chúng sẽ làm hỏng hook staleness detection và khiến mọi commit đều trigger `FULL_UPDATE`.
- Nếu review có yêu cầu khác về `.ua/.understandignore`, đổi quyết định trước khi commit.

## Validation
```bash
git ls-files .ua
git check-ignore -v .ua/tmp/ua-structure.json
git check-ignore -v .ua/intermediate/batches.json
git check-ignore -v .ua/meta.json || echo "must not ignore meta.json"
git check-ignore -v .ua/fingerprints.json || echo "must not ignore fingerprints.json"
```

## Rollback
- `git switch main && git branch -D chore/gitignore-ua-temp && git push origin --delete chore/gitignore-ua-temp -f` nếu muốn hủy toàn bộ nhánh
- Hoặc revert commit cụ thể nếu gặp lỗi đánh review
