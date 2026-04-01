import ActivityKit
import Foundation

/// Task-based Live Activity attributes.
/// Dynamic Island ve Lock Screen'de AI task ilerlemesini gosterir.
/// Widget Extension ile shared kullanilir.
struct TaskActivityAttributes: ActivityAttributes {
    /// Degisen veriler — task calisirken guncellenir (APNs push ile de).
    public struct ContentState: Codable, Hashable {
        /// Mevcut task durumu (ornegin "planning", "implementing", "testing").
        var status: String
        /// Mevcut adim aciklamasi.
        var currentStep: String
        /// Ilerleme orani (0.0 - 1.0).
        var progress: Double
        /// Tamamlanan adim sayisi.
        var completedSteps: Int
        /// Toplam adim sayisi.
        var totalSteps: Int
        /// Tahmini kalan sure (saniye). Nil ise bilinmiyor.
        var estimatedSecondsRemaining: Int?
        /// Faz ikonu (SF Symbol adi).
        var phaseIcon: String
    }

    /// Task benzersiz kimligi (degismez).
    var taskId: String
    /// Task basligi (degismez).
    var taskTitle: String
    /// Proje adi (degismez).
    var projectName: String
}
