import Foundation
import os
import Security

/// Keychain hata tipleri.
enum KeychainError: Error, Sendable {
    case saveFailed(OSStatus)
    case readFailed(OSStatus)
    case deleteFailed(OSStatus)
    case unexpectedData
}

/// JWT token'lari Keychain'de guvenli saklamak icin yardimci sinif.
/// UserDefaults yerine Keychain kullanarak token guvenligini saglar.
final class KeychainHelper: Sendable {
    private let service: String
    private let logger = Logger(
        subsystem: "com.rafraf",
        category: "KeychainHelper"
    )

    init(service: String = "com.rafraf.auth") {
        self.service = service
    }

    /// Keychain'e veri kaydeder.
    /// - Parameters:
    ///   - data: Kaydedilecek veri.
    ///   - key: Keychain anahtari.
    func save(_ data: Data, for key: String) throws {
        // Onceki degeri sil
        let deleteQuery: [String: AnyHashable] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
        SecItemDelete(deleteQuery as CFDictionary)

        let addQuery: [String: AnyHashable] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        ]

        let status = SecItemAdd(addQuery as CFDictionary, nil)
        guard status == errSecSuccess else {
            logger.error("Keychain kayit hatasi: \(status)")
            throw KeychainError.saveFailed(status)
        }
        logger.debug("Keychain'e kaydedildi: \(key)")
    }

    /// Keychain'e string deger kaydeder.
    /// - Parameters:
    ///   - value: Kaydedilecek string.
    ///   - key: Keychain anahtari.
    func saveString(_ value: String, for key: String) throws {
        guard let data = value.data(using: .utf8) else {
            throw KeychainError.unexpectedData
        }
        try save(data, for: key)
    }

    /// Keychain'den veri okur.
    /// - Parameter key: Keychain anahtari.
    /// - Returns: Okunan veri veya nil.
    func read(for key: String) -> Data? {
        let query: [String: AnyHashable] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        guard status == errSecSuccess else {
            if status != errSecItemNotFound {
                logger.error("Keychain okuma hatasi: \(status)")
            }
            return nil
        }

        return result as? Data
    }

    /// Keychain'den string deger okur.
    /// - Parameter key: Keychain anahtari.
    /// - Returns: Okunan string veya nil.
    func readString(for key: String) -> String? {
        guard let data = read(for: key) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    /// Keychain'den veri siler.
    /// - Parameter key: Keychain anahtari.
    func delete(for key: String) throws {
        let query: [String: AnyHashable] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]

        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            logger.error("Keychain silme hatasi: \(status)")
            throw KeychainError.deleteFailed(status)
        }
        logger.debug("Keychain'den silindi: \(key)")
    }

    /// Tum servise ait verileri siler.
    func deleteAll() throws {
        let query: [String: AnyHashable] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
        ]

        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            logger.error("Keychain toplu silme hatasi: \(status)")
            throw KeychainError.deleteFailed(status)
        }
        logger.debug("Keychain tamamen temizlendi")
    }
}
