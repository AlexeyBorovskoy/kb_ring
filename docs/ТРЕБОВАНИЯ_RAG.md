# Требования к RAG (из документов shared_vm)

Исходники:
- `/home/alexey/shared_vm/запросы по kb.txt`
- `/home/alexey/shared_vm/Ответы системы.txt`

## Обязательные ограничения

- Режим **search-only** должен работать **без** LLM.
- Режим **rag** вызывает ChatGPT/OpenAI **только после** retrieval.
- Запрещено отправлять в LLM целые документы.
- Ограничение контекста: **не более 20 чанков**.
- Если данных недостаточно, ответ должен быть честным: `"данные не найдены"`.
- Каждый RAG-ответ должен возвращать **источники** (citations) и ссылаться на реальные документы/чанки.

## API (текущая реализация)

- `POST /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions/{id}`
- `POST /api/v1/chat/sessions/{id}/message` с `mode=search|rag`

## Хранение

- `chat.sessions` / `chat.messages` / `chat.message_citations` / `chat.session_memory`
- citations связывают `assistant` сообщение с `tac.chunks.id`
- `tac.documents.uri` используется как “каноническая ссылка” на источник

