# TG -> KB-RING ETL (шаг 1): материализация "всего" в tac.documents

Требование: на шаге 1 проиндексировать TG целиком:
- сообщения
- дайджесты
- вложения (минимум: pdf/сканы, jpg/png, docx, txt/md/html)
- OCR обязателен (cloud OCR ключи из TG стека), обработка последовательная

## Подход (минимальный, но рабочий)

1. Восстановить TG дамп в схему `tg.*` в БД `kb_ring`.
2. Добавить ETL-скрипт/джобы, которые:
   - выбирают записи из `tg.*` таблиц
   - формируют документы `tac.documents`:
     - `source='tg'`
     - `source_ref` = стабильный идентификатор (таблица+id)
     - `doc_type` = `message|digest|attachment`
     - `title` = разумный заголовок (chat title + timestamp + id)
     - `uri` = web URL через портал (на домене kb.*) на конкретную сущность
     - `body_text` = текст (или OCR/extract результат)
     - `meta` = JSON с исходными полями (chat_id, msg_id, file_id, mime, etc)
   - ставят `op.jobs(kind='index_document')` на каждый документ (chunk/embeddings/NER)

## Важное

- Для вложений:
  - если это текстовый формат (txt/md/html/docx) -> extract text локально
  - если pdf/image -> OCR через cloud OCR (sequential)
- Пропускать неизмененные: привязка по `content_sha256` (или по исходному hash/file_id+size+mtime).

