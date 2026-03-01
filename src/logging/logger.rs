use log::{Level, Metadata, Record};
use pyo3::exceptions::PyRuntimeError;
use pyo3::intern;
use pyo3::prelude::*;
use pyo3::sync::{MutexExt, PyOnceLock};
use pyo3::types::{PyDict, PyInt};
use std::sync::{Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::sync::mpsc::{Receiver, Sender, channel};

struct LogEntry {
    level: Level,
    target: String,
    message: String,
    timestamp: SystemTime,
}

struct Channel {
    sender: Sender<LogEntry>,
    receiver: Mutex<Receiver<LogEntry>>,
}

const CHANNEL_BUFFER_SIZE: usize = 10000;
static CHANNEL: OnceLock<Channel> = OnceLock::new();

struct GlobalLogger;
impl log::Log for GlobalLogger {
    fn enabled(&self, _metadata: &Metadata) -> bool {
        true
    }

    fn log(&self, record: &Record) {
        let Some(channel) = CHANNEL.get() else {
            return; // Logging is not initialized yet
        };

        let entry = LogEntry {
            level: record.level(),
            target: record.target().to_string(),
            message: format!("{}", record.args()),
            timestamp: SystemTime::now(),
        };
        let _ = channel.sender.try_send(entry);
    }

    fn flush(&self) {}
}

static LOGGER: GlobalLogger = GlobalLogger;

pub fn py_logger<'py>(py: Python<'py>, target: &str) -> PyResult<Bound<'py, PyAny>> {
    static GET_LOGGER: PyOnceLock<Py<PyAny>> = PyOnceLock::new();
    static TIMESTAMPER: PyOnceLock<Py<PyAny>> = PyOnceLock::new();
    static LOGGERS_DICT: PyOnceLock<Py<PyDict>> = PyOnceLock::new();

    let loggers = LOGGERS_DICT.get_or_init(py, || PyDict::new(py).unbind()).bind(py);
    if let Some(logger) = loggers.get_item(target)? {
        return Ok(logger);
    }

    let logger = GET_LOGGER.import(py, "logging", "getLogger")?.call1((target,))?;

    let timestamper = TIMESTAMPER
        .import(py, "pyreqwest.logging._internal", "Timestamper")?
        .call0()?;
    logger.call_method1("addFilter", (timestamper,))?;

    loggers.set_item(target, &logger)?;
    Ok(logger)
}

fn py_logger_extra_kwarg<'py>(py: Python<'py>, entry: &LogEntry) -> PyResult<Bound<'py, PyDict>> {
    static START_TIME: PyOnceLock<Py<PyInt>> = PyOnceLock::new();
    let start_time = START_TIME.import(py, "pyreqwest", "_start_time_ns")?;
    let timestamp = entry
        .timestamp
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();

    let extra = PyDict::new(py);
    extra.set_item(intern!(py, "_pyreqwest_start_time"), start_time)?;
    extra.set_item(intern!(py, "_pyreqwest_log_timestamp"), timestamp)?;
    let kwargs = PyDict::new(py);
    kwargs.set_item(intern!(py, "extra"), &extra)?;
    Ok(kwargs)
}

fn py_log(py: Python, entry: LogEntry) -> PyResult<()> {
    let logger = py_logger(py, &entry.target)?;

    let py_level = match entry.level {
        Level::Error => 40, // Corresponds to logging.ERROR, etc.
        Level::Warn => 30,
        Level::Info => 20,
        Level::Debug | Level::Trace => 10,
    };

    let kwargs = py_logger_extra_kwarg(py, &entry)?;
    logger.call_method(intern!(py, "log"), (py_level, entry.message), Some(&kwargs))?;
    Ok(())
}

fn pop_entries(py: Option<Python>, count: Option<usize>) -> Option<Vec<LogEntry>> {
    let Some(channel) = CHANNEL.get() else {
        return None; // Logging isn't initialized yet
    };

    let receiver_lock = if let Some(py) = py {
        channel.receiver.lock_py_attached(py).ok()
    } else {
        channel.receiver.lock().ok()
    };
    let Some(mut receiver) = receiver_lock else {
        return None; // Just skip on the poisoned lock
    };

    let mut entries = Vec::with_capacity(receiver.len().min(count.unwrap_or(usize::MAX)));
    while let Ok(entry) = receiver.try_recv() {
        entries.push(entry);
        if let Some(max_count) = count
            && entries.len() >= max_count
        {
            break;
        }
    }
    if entries.is_empty() { None } else { Some(entries) }
}

pub fn init_verbose_logging() -> PyResult<()> {
    if CHANNEL.get().is_some() {
        return Ok(()); // Already initialized (fast path without init)
    }
    let (tx, rx) = channel(CHANNEL_BUFFER_SIZE);
    let channel = Channel {
        sender: tx,
        receiver: Mutex::new(rx),
    };
    if CHANNEL.set(channel).is_err() {
        return Ok(()); // Already initialized
    }

    log::set_logger(&LOGGER).map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
    log::set_max_level(log::LevelFilter::Trace);
    Ok(())
}

pub fn flush_logs_no_gil() -> PyResult<()> {
    // Process in batches to avoid holding GIL too long
    while let Some(entries) = pop_entries(None, Some(1000)) {
        Python::attach(|py| entries.into_iter().try_for_each(|log| py_log(py, log)))?;
    }
    Ok(())
}

#[pyfunction]
pub fn flush_logs(py: Python) -> PyResult<()> {
    if let Some(entries) = pop_entries(Some(py), None) {
        entries.into_iter().try_for_each(|log| py_log(py, log))?;
    }
    Ok(())
}
