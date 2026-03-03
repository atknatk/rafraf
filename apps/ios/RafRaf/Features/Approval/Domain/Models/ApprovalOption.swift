import Foundation

/// Onay secenegi domain modeli.
/// Kullaniciya gosterilen buton secenegini temsil eder.
struct ApprovalOption: Identifiable, Sendable, Equatable {
    /// Secenek tanimlayicisi (approve, reject, detail vb.)
    let id: String
    /// Kullaniciya gosterilen etiket metni.
    let label: String
    /// Buton gosterim stili.
    let style: ApprovalOptionStyle
}

/// Onay secenegi buton stili.
enum ApprovalOptionStyle: String, Sendable, Equatable, CaseIterable {
    /// Birincil aksiyon (onay vb.)
    case primary
    /// Tehlikeli aksiyon (reddetme vb.)
    case danger
    /// Ikincil aksiyon (detay, iptal vb.)
    case secondary
}
