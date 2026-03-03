import Foundation

/// Onay sorusu domain modeli.
/// Backend'den gelen interaktif onay talebini temsil eder.
struct ApprovalQuestion: Identifiable, Sendable, Equatable {
    /// Benzersiz onay talebi ID'si (UUID).
    let id: String
    /// Kullaniciya gosterilecek soru metni.
    let question: String
    /// Soruya ek bilgi/baglam (opsiyonel).
    let context: String?
    /// Kullanicinin secebilecegi secenek listesi.
    let options: [ApprovalOption]
    /// Onay bekleme suresi (saniye).
    let timeoutSeconds: Int
    /// Onay kategorisi (deploy, destructive, infrastructure, write_remote).
    let category: ApprovalCategory
    /// Sorunun alindigi zaman.
    let receivedAt: Date
}

/// Onay kategorisi.
/// `docs/07_Security_Permissions_Cost_Analysis.md` Bolum 3.2'ye uygun.
enum ApprovalCategory: String, Sendable, Equatable, CaseIterable {
    case deploy
    case destructive
    case infrastructure
    case writeRemote = "write_remote"
}

/// Kullanici onay karari.
enum ApprovalDecision: String, Sendable, Equatable {
    case approved
    case rejected
}
