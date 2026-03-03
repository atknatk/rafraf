import Foundation

/// Ayarlar repository protokolu.
/// Domain katmani Data katmanindan izole kalir; bu protokol uzerinden iletisir.
protocol SettingsRepositoryProtocol: Sendable {
    /// Mevcut uygulama ayarlarini yukler.
    func loadSettings() -> AppSettings

    /// Uygulama ayarlarini kaydeder.
    /// - Parameter settings: Kaydedilecek ayarlar.
    func saveSettings(_ settings: AppSettings)

    /// Tek bir ayar degerini gunceller.
    /// - Parameters:
    ///   - keyPath: Guncellenecek ayar yolu.
    ///   - value: Yeni deger.
    func updateSetting<Value: Sendable>(
        _ keyPath: WritableKeyPath<AppSettings, Value>,
        value: Value
    )
}
