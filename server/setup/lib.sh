#!/usr/bin/env bash
# LC v0.1 — общая библиотека установщика.
# Источники: server/setup/lib.sh (в репозитории и в установленном дереве).
# Подключается: bootstrap install.sh, scripts/lc.sh (через APP_ROOT/setup/lib.sh).

LC_REPO="${LC_REPO:-NoTimeToSleep-Team/esp32chat}"

lc_log() {
    # ВАЖНО: в stderr. stdout у функций качалки занят под результат (путь пакета).
    echo "[lc] $(date '+%H:%M:%S') $*" >&2
}

lc_fail() {
    lc_log "ОШИБКА: $*" >&2
    exit 1
}

# Возвращает URL релизного тарбола:
#   1) LC_TARBALL_URL (URL или локальный путь, включая file://);
#   2) конкретная версия LC_VERSION -> releases/tags/v<ver>;
#   3) последний релиз на GitHub.
lc_release_url() {
    if [[ -n "${LC_TARBALL_URL:-}" ]]; then
        printf '%s' "${LC_TARBALL_URL}"
        return 0
    fi

    local api_url
    if [[ -n "${LC_VERSION:-}" ]]; then
        api_url="https://api.github.com/repos/${LC_REPO}/releases/tags/v${LC_VERSION}"
    else
        api_url="https://api.github.com/repos/${LC_REPO}/releases/latest"
    fi

    local json url
    json="$(curl -fsSL --retry 3 "${api_url}")" \
        || lc_fail "не удалось получить информацию о релизе (${api_url})"
    url="$(printf '%s' "${json}" \
        | sed -n 's/.*"browser_download_url": *"\([^"]*lc-server[^"]*\.tar\.gz\)".*/\1/p' \
        | head -1)"
    [[ -n "${url}" ]] || lc_fail "в релизе не найден тарбол lc-server-*.tar.gz"
    printf '%s' "${url}"
}

# Качает тарбол + .sha256, проверяет, распаковывает в $1 и печатает корень пакета.
lc_fetch_release() {
    local dest_dir="$1"
    local url sha_url tarball pkg_root

    url="$(lc_release_url)"
    sha_url="${url}.sha256"
    tarball="${dest_dir}/$(basename "${url}")"
    mkdir -p "${dest_dir}"

    lc_log "скачиваю ${url}"
    curl -fsSL --retry 3 -o "${tarball}" "${url}" \
        || lc_fail "не удалось скачать тарбол: ${url}"

    if ! curl -fsSL --retry 3 -o "${tarball}.sha256" "${sha_url}"; then
        rm -f "${tarball}.sha256"
        if [[ "${LC_SKIP_SHA:-0}" == "1" ]]; then
            lc_log "ВНИМАНИЕ: sha256 не проверен (файл недоступен, LC_SKIP_SHA=1)"
        else
            lc_fail "не удалось скачать контрольную сумму: ${sha_url}"
        fi
    else
        ( cd "${dest_dir}" && sha256sum -c "$(basename "${tarball}").sha256" ) >&2 \
            || lc_fail "контрольная сумма тарбола не сошлась"
        lc_log "sha256 проверен"
    fi

    tar -xzf "${tarball}" -C "${dest_dir}" \
        || lc_fail "не удалось распаковать тарбол"
    pkg_root="$(tar -tzf "${tarball}" | head -1 | cut -d/ -f1)"
    [[ -n "${pkg_root}" ]] || lc_fail "пустой тарбол"
    rm -f "${tarball}" "${tarball}.sha256"
    printf '%s' "${dest_dir}/${pkg_root}"
}
