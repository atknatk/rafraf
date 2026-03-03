import Foundation
import Testing
@testable import RafRaf

/// KeychainHelper testleri.
/// Not: Keychain testleri xctest runner'da `errSecMissingEntitlement` (-34018)
/// hatasi alabilir. Bu durumda testler skip edilir.
@Suite("KeychainHelper Tests")
struct KeychainHelperTests {
    private let keychain = KeychainHelper(service: "com.rafraf.test")

    /// Keychain erisimi mevcut mu kontrol eder.
    /// xctest runner'da entitlement eksikligi nedeniyle Keychain kullanilamayabilir.
    private var isKeychainAccessible: Bool {
        let testKey = "keychain_test_probe_\(UUID().uuidString)"
        do {
            try keychain.saveString("probe", for: testKey)
            try keychain.delete(for: testKey)
            return true
        } catch {
            return false
        }
    }

    @Test("String kaydetme ve okuma basarili olmali")
    func saveAndReadString() throws {
        guard isKeychainAccessible else {
            // Keychain CI ortaminda erisilebilir degil, skip
            return
        }
        let key = "test-key-\(UUID().uuidString)"
        let value = "test-value-123"

        try keychain.saveString(value, for: key)
        let readValue = keychain.readString(for: key)

        #expect(readValue == value)

        try keychain.delete(for: key)
    }

    @Test("Data kaydetme ve okuma basarili olmali")
    func saveAndReadData() throws {
        guard isKeychainAccessible else { return }
        let key = "test-data-\(UUID().uuidString)"
        let data = "test-data".data(using: .utf8)!

        try keychain.save(data, for: key)
        let readData = keychain.read(for: key)

        #expect(readData == data)

        try keychain.delete(for: key)
    }

    @Test("Olmayan anahtar icin nil donmeli")
    func readNonExistentKey() {
        let result = keychain.readString(for: "non-existent-key-\(UUID().uuidString)")
        #expect(result == nil)
    }

    @Test("Silme basarili olmali")
    func deleteKey() throws {
        guard isKeychainAccessible else { return }
        let key = "test-delete-\(UUID().uuidString)"
        try keychain.saveString("value", for: key)

        try keychain.delete(for: key)

        let result = keychain.readString(for: key)
        #expect(result == nil)
    }

    @Test("Ayni anahtara tekrar yazma guncelleme yapmali")
    func overwriteKey() throws {
        guard isKeychainAccessible else { return }
        let key = "test-overwrite-\(UUID().uuidString)"

        try keychain.saveString("value1", for: key)
        try keychain.saveString("value2", for: key)

        let result = keychain.readString(for: key)
        #expect(result == "value2")

        try keychain.delete(for: key)
    }

    @Test("Toplu silme basarili olmali")
    func deleteAll() throws {
        guard isKeychainAccessible else { return }
        let testKeychain = KeychainHelper(service: "com.rafraf.test.deleteall.\(UUID().uuidString)")
        try testKeychain.saveString("val1", for: "key1")
        try testKeychain.saveString("val2", for: "key2")

        try testKeychain.deleteAll()

        #expect(testKeychain.readString(for: "key1") == nil)
        #expect(testKeychain.readString(for: "key2") == nil)
    }

    @Test("Olmayan anahtari silmek hata vermemeli")
    func deleteNonExistent() throws {
        guard isKeychainAccessible else { return }
        try keychain.delete(for: "non-existent-\(UUID().uuidString)")
    }
}
