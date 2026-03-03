import Foundation

/// Screenshot viewer durumu.
enum ScreenshotViewerState: Sendable, Equatable {
    /// Gorsel yukleniyor.
    case loading
    /// Gorsel basariyla yuklendi.
    case loaded
    /// Gorsel yuklenirken hata olustu.
    case error(String)
}
