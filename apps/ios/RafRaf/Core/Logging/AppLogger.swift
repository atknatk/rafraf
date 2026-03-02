import os

/// Uygulama loglama yardimcisi.
/// os.Logger wrapper - subsystem sabiti ile category bazli loglama saglar.
enum AppLogger {
    /// Belirtilen kategori icin Logger olusturur.
    /// - Parameter category: Log kategorisi (feature adi, katman adi vb.)
    /// - Returns: Konfigure edilmis Logger instance.
    static func logger(for category: String) -> Logger {
        Logger(subsystem: "com.rafraf", category: category)
    }
}
