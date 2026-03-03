import Foundation

/// Dosya yukleme ilerleme durumu.
/// URLSession delegate ile gercek zamanli guncellenir.
struct FileUploadProgress: Sendable, Equatable {
    /// Dosya ID'si.
    let fileId: String
    /// Dosya adi.
    let fileName: String
    /// Toplam dosya boyutu (bytes).
    let totalBytes: Int64
    /// Yuklenen boyut (bytes).
    let uploadedBytes: Int64
    /// Ilerleme orani (0.0 - 1.0).
    let progress: Double
    /// Yukleme tamamlandi mi.
    let isCompleted: Bool
    /// Hata mesaji (varsa).
    let error: String?

    /// Ilerleme yuzdesini dondurur (0 - 100).
    var progressPercentage: Int {
        Int(progress * 100)
    }
}
