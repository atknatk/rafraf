import Foundation
import LocalAuthentication
import os

/// Biyometrik dogrulama hata tipleri.
enum BiometricError: Error, Sendable {
    case notAvailable
    case notEnrolled
    case authenticationFailed
    case cancelled
    case systemError(String)
}

/// Biyometrik dogrulama tipi.
enum BiometricType: Sendable {
    case none
    case touchID
    case faceID
    case opticID
}

/// Face ID / Touch ID ile biyometrik dogrulama yoneticisi.
/// LocalAuthentication framework kullanir.
final class BiometricAuthManager: Sendable {
    private let logger = Logger(
        subsystem: "com.rafraf",
        category: "BiometricAuth"
    )

    /// Cihazda mevcut biyometrik dogrulama tipini dondurur.
    var availableBiometricType: BiometricType {
        let context = LAContext()
        var error: NSError?

        guard context.canEvaluatePolicy(
            .deviceOwnerAuthenticationWithBiometrics,
            error: &error
        ) else {
            return .none
        }

        switch context.biometryType {
        case .touchID:
            return .touchID
        case .faceID:
            return .faceID
        case .opticID:
            return .opticID
        case .none:
            return .none
        @unknown default:
            return .none
        }
    }

    /// Biyometrik dogrulama mevcut mu kontrol eder.
    var isBiometricAvailable: Bool {
        availableBiometricType != .none
    }

    /// Biyometrik dogrulama baslatir.
    /// - Parameter reason: Kullaniciya gosterilecek dogrulama nedeni.
    /// - Throws: BiometricError
    func authenticate(reason: String) async throws {
        let context = LAContext()
        var error: NSError?

        guard context.canEvaluatePolicy(
            .deviceOwnerAuthenticationWithBiometrics,
            error: &error
        ) else {
            logger.warning("Biyometrik dogrulama mevcut degil")
            if let error {
                throw mapLAError(error)
            }
            throw BiometricError.notAvailable
        }

        do {
            let success = try await context.evaluatePolicy(
                .deviceOwnerAuthenticationWithBiometrics,
                localizedReason: reason
            )
            if success {
                logger.info("Biyometrik dogrulama basarili")
            } else {
                logger.warning("Biyometrik dogrulama basarisiz")
                throw BiometricError.authenticationFailed
            }
        } catch let laError as LAError {
            logger.error("Biyometrik hata: \(laError.localizedDescription)")
            throw mapLAError(laError as NSError)
        }
    }

    // MARK: - Private

    private func mapLAError(_ error: NSError) -> BiometricError {
        let laErrorCode = LAError.Code(rawValue: error.code)
        switch laErrorCode {
        case .biometryNotAvailable:
            return .notAvailable
        case .biometryNotEnrolled:
            return .notEnrolled
        case .userCancel, .appCancel, .systemCancel:
            return .cancelled
        case .authenticationFailed:
            return .authenticationFailed
        default:
            return .systemError(error.localizedDescription)
        }
    }
}
