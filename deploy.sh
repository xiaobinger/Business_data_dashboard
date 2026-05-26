#!/bin/bash
APP_NAME="data_dashboard"
APP_DIR="/opt/data_dashboard"
LOG_DIR="${APP_DIR}/logs"
PID_FILE="${APP_DIR}/${APP_NAME}.pid"
MAIN="main.py"
HOST="0.0.0.0"
PORT=5000

mkdir -p "${LOG_DIR}"

get_pid() {
    if [ -f "${PID_FILE}" ]; then
        cat "${PID_FILE}"
    fi
}

is_running() {
    local pid=$(get_pid)
    if [ -n "${pid}" ]; then
        kill -0 "${pid}" 2>/dev/null
        return $?
    fi
    return 1
}

stop_app() {
    local pid=$(get_pid)
    if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
        echo "Stopping ${APP_NAME} (PID: ${pid})..."
        kill "${pid}"
        for i in $(seq 1 10); do
            if ! kill -0 "${pid}" 2>/dev/null; then
                echo "${APP_NAME} stopped."
                rm -f "${PID_FILE}"
                return 0
            fi
            sleep 1
        done
        echo "Force killing ${APP_NAME}..."
        kill -9 "${pid}" 2>/dev/null
        rm -f "${PID_FILE}"
    else
        echo "${APP_NAME} is not running."
    fi
}

start_app() {
    if is_running; then
        echo "${APP_NAME} is already running (PID: $(get_pid))"
        return 1
    fi

    cd "${APP_DIR}"

    if [ ! -d "venv" ]; then
        echo "Creating virtual environment..."
        python3 -m venv venv
    fi

    source venv/bin/activate

    echo "Installing dependencies..."
    pip install -r requirements.txt -q

    local today=$(date +%Y-%m-%d)
    local log_file="${LOG_DIR}/${APP_NAME}_${today}.log"

    echo "Starting ${APP_NAME}..."
    nohup python "${MAIN}" >> "${log_file}" 2>&1 &
    local pid=$!
    echo "${pid}" > "${PID_FILE}"

    sleep 2
    if kill -0 "${pid}" 2>/dev/null; then
        echo "${APP_NAME} started (PID: ${pid}), log: ${log_file}"
    else
        echo "Failed to start ${APP_NAME}, check ${log_file}"
        rm -f "${PID_FILE}"
        return 1
    fi
}

rotate_logs() {
    local keep_days=${1:-30}
    echo "Rotating logs, keeping ${keep_days} days..."
    find "${LOG_DIR}" -name "${APP_NAME}_*.log" -mtime +${keep_days} -delete
    echo "Done."
}

status_app() {
    if is_running; then
        echo "${APP_NAME} is running (PID: $(get_pid))"
    else
        echo "${APP_NAME} is not running."
    fi
}

tail_log() {
    local today=$(date +%Y-%m-%d)
    local log_file="${LOG_DIR}/${APP_NAME}_${today}.log"
    if [ -f "${log_file}" ]; then
        tail -f "${log_file}"
    else
        echo "No log file for today: ${log_file}"
    fi
}

case "$1" in
    start)
        start_app
        ;;
    stop)
        stop_app
        ;;
    restart)
        stop_app
        sleep 1
        start_app
        ;;
    status)
        status_app
        ;;
    log)
        tail_log
        ;;
    rotate)
        rotate_logs ${2:-30}
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|log|rotate [days]}"
        exit 1
        ;;
esac
