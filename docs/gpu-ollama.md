# Ollama GPU Checks

## Быстрые проверки

Проверь, что Docker вообще видит NVIDIA GPU:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

Проверь GPU внутри контейнера `ollama`:

```bash
docker compose exec ollama nvidia-smi
```

Проверь логи Ollama на признаки offload в GPU:

```bash
docker compose logs ollama | grep -E "GPU|offloaded|device="
```

## Что смотреть в health

Backend теперь возвращает `llm_device` в `/health`, `/api/health` и `/admin/health`.

- `gpu` — у запущенной модели есть VRAM-offload.
- `cpu` — модель загружена без VRAM, Ollama реально работает на CPU.
- `unknown` — модель ещё не загружена или Ollama не ответила на быстрый probe.

Если ожидался GPU, а health показывает `llm_device=cpu`, проверь:

- установлен ли NVIDIA Container Toolkit;
- доступна ли GPU в Docker через `--gpus all`;
- загрузилась ли модель в Ollama после старта;
- нет ли fallback на CPU из-за драйвера или нехватки VRAM.
