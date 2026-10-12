#!/usr/bin/env python3
"""Schema-driven installer helper (v0.1, pure stdlib, python>=3.10).

Bash-движки (install_pi.sh, wizard.sh) читают манифест settings-schema.json
только через этот модуль: поля мастера, дефолты, базовые LCS_*-настройки,
apt-пакеты, минимальная версия Python, валидация и запись значений в app.env.

Команды:
    manifest.py min_python                       -> строка версии
    manifest.py apt_packages                     -> пакеты через пробел
    manifest.py base_env                         -> KEY=VALUE (по строке на пару)
    manifest.py defaults                         -> KEY=VALUE дефолтов полей
    manifest.py fields [ru|en]                   -> TSV: key, type, section, label,
                                                    default, choices, required_if,
                                                    confirm, persist
    manifest.py choices KEY [ru|en]              -> строки "значение<TAB>подпись"
    manifest.py validate KEY VALUE               -> 0/1, ошибка в stderr
    manifest.py set-env ENV_FILE KEY VALUE       -> вписать/обновить пару в KEY=VALUE файл
"""

import json
import sys
from pathlib import Path


def load(path: str | None = None) -> dict:
    schema_path = Path(path) if path else Path(__file__).resolve().parent / "settings-schema.json"
    with open(schema_path, encoding="utf-8") as handle:
        return json.load(handle)


def label_of(field: dict, lang: str) -> str:
    if lang == "ru" and field.get("label_ru"):
        return field["label_ru"]
    return field.get("label") or field.get("label_ru") or field["key"]


def _flag(value) -> str:
    if value is True:
        return "1"
    if value is False:
        return "0"
    return str(value or "-")


def cmd_min_python(schema: dict) -> int:
    print(schema["min_python"])
    return 0


def cmd_apt_packages(schema: dict) -> int:
    print(" ".join(schema["apt_packages"]))
    return 0


def cmd_base_env(schema: dict) -> int:
    for key, value in schema.get("base_env", {}).items():
        print(f"{key}={value}")
    return 0


def cmd_defaults(schema: dict) -> int:
    for field in schema.get("fields", []):
        if field.get("default") is not None:
            print(f"{field['key']}={field['default']}")
    return 0


def cmd_fields(schema: dict, lang: str) -> int:
    # Разделитель \x1f (unit separator): TAB использовать нельзя — bash `read`
    # схлопывает подряд идущие IFS-whitespace, а у нас есть пустые колонки.
    for field in schema.get("fields", []):
        columns = [
            field["key"],
            field.get("type", "text"),
            field.get("section", "general"),
            label_of(field, lang),
            str(field.get("default", "")),
            ",".join(field.get("choices", [])),
            _flag(field.get("required_if")),
            _flag(field.get("confirm")),
            _flag(field.get("persist")),
        ]
        print("\x1f".join(columns))
    return 0


def cmd_choices(schema: dict, key: str, lang: str) -> int:
    field = next((f for f in schema.get("fields", []) if f["key"] == key), None)
    if field is None:
        print(f"unknown field: {key}", file=sys.stderr)
        return 1
    choices = field.get("choices", [])
    translated = field.get("choices_ru" if lang == "ru" else "choices", []) or []
    for index, value in enumerate(choices):
        label = translated[index] if index < len(translated) else value
        print(f"{value}\x1f{label}")
    return 0


def cmd_validate(schema: dict, key: str, value: str) -> int:
    field = next((f for f in schema.get("fields", []) if f["key"] == key), None)
    if field is None:
        print(f"unknown field: {key}", file=sys.stderr)
        return 1

    field_type = field.get("type", "text")
    text = value.strip()

    if field_type == "int":
        try:
            number = int(text)
        except ValueError:
            print("must be an integer", file=sys.stderr)
            return 1
        if "min" in field and number < field["min"]:
            print(f"too small (min {field['min']})", file=sys.stderr)
            return 1
        if "max" in field and number > field["max"]:
            print(f"too big (max {field['max']})", file=sys.stderr)
            return 1
        return 0

    if field_type in ("text", "password"):
        if field.get("required") and not text:
            print("must not be empty", file=sys.stderr)
            return 1
        if "minlen" in field and len(text) < field["minlen"]:
            print(f"too short (min {field['minlen']} characters)", file=sys.stderr)
            return 1
        if "maxlen" in field and len(text) > field["maxlen"]:
            print(f"too long (max {field['maxlen']} characters)", file=sys.stderr)
            return 1
        return 0

    if field_type == "bool":
        if text.lower() not in ("1", "0", "true", "false", "yes", "no", "on", "off"):
            print("must be yes/no", file=sys.stderr)
            return 1
        return 0

    if field_type == "choice":
        if field.get("required") and not text:
            print("must not be empty", file=sys.stderr)
            return 1
        if field.get("choices") and text not in field["choices"]:
            print("must be one of: " + ", ".join(field["choices"]), file=sys.stderr)
            return 1
        return 0

    print(f"unsupported field type: {field_type}", file=sys.stderr)
    return 1


def cmd_set_env(schema: dict, env_file: str, key: str, value: str) -> int:
    path = Path(env_file)
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    found = False
    out: list[str] = []
    for line in lines:
        if line.startswith(key + "="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 1
    command = argv[0]
    schema = load()
    if command == "min_python":
        return cmd_min_python(schema)
    if command == "apt_packages":
        return cmd_apt_packages(schema)
    if command == "base_env":
        return cmd_base_env(schema)
    if command == "defaults":
        return cmd_defaults(schema)
    if command == "fields":
        return cmd_fields(schema, argv[1] if len(argv) > 1 else "ru")
    if command == "choices":
        if len(argv) < 2:
            print("usage: manifest.py choices KEY [ru|en]", file=sys.stderr)
            return 1
        return cmd_choices(schema, argv[1], argv[2] if len(argv) > 2 else "ru")
    if command == "validate":
        if len(argv) < 3:
            print("usage: manifest.py validate KEY VALUE", file=sys.stderr)
            return 1
        return cmd_validate(schema, argv[1], argv[2])
    if command == "set-env":
        if len(argv) < 4:
            print("usage: manifest.py set-env ENV_FILE KEY VALUE", file=sys.stderr)
            return 1
        return cmd_set_env(schema, argv[1], argv[2], argv[3])
    print(f"unknown command: {command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
