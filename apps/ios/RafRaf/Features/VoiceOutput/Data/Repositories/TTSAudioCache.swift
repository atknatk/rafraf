import Foundation
import os

/// TTS ses verisi cache yoneticisi.
/// NSCache (memory) + FileManager (disk) ile iki katmanli cache.
actor TTSAudioCache {
    private let memoryCache = NSCache<NSString, NSData>()
    private let diskCacheURL: URL
    private let logger = AppLogger.logger(for: "TTSAudioCache")

    /// Maksimum memory cache boyutu (50 MB).
    private static let maxMemoryCost = 50 * 1024 * 1024
    /// Maksimum disk cache boyutu (200 MB).
    private static let maxDiskCacheSize = 200 * 1024 * 1024
    /// Cache item TTL (7 gun).
    private static let cacheExpirationInterval: TimeInterval = 7 * 24 * 60 * 60

    init() {
        let cacheDir = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        let diskURL = cacheDir.appendingPathComponent("TTSAudioCache", isDirectory: true)
        self.diskCacheURL = diskURL

        // Memory cache limiti
        memoryCache.totalCostLimit = Self.maxMemoryCost
        memoryCache.countLimit = 100

        // Disk cache dizini olustur (nonisolated context - dogrudan FileManager kullan)
        if !FileManager.default.fileExists(atPath: diskURL.path) {
            try? FileManager.default.createDirectory(at: diskURL, withIntermediateDirectories: true)
        }
    }

    // MARK: - Public API

    /// Cache'den ses verisini dondurur.
    /// - Parameter key: Cache anahtari (metin hash'i).
    /// - Returns: Cache'deki ses verisi veya nil.
    func get(for key: String) -> Data? {
        let cacheKey = cacheKey(for: key)

        // Memory cache kontrolu
        if let data = memoryCache.object(forKey: cacheKey as NSString) {
            logger.debug("Memory cache hit: \(key.prefix(30))")
            return data as Data
        }

        // Disk cache kontrolu
        let fileURL = diskFileURL(for: cacheKey)
        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            return nil
        }

        // TTL kontrolu
        if let attributes = try? FileManager.default.attributesOfItem(atPath: fileURL.path),
           let modifiedDate = attributes[.modificationDate] as? Date,
           Date().timeIntervalSince(modifiedDate) > Self.cacheExpirationInterval {
            // Cache expired, dosyayi sil
            try? FileManager.default.removeItem(at: fileURL)
            return nil
        }

        do {
            let data = try Data(contentsOf: fileURL)
            // Memory cache'e de ekle
            memoryCache.setObject(data as NSData, forKey: cacheKey as NSString, cost: data.count)
            logger.debug("Disk cache hit: \(key.prefix(30))")
            return data
        } catch {
            logger.warning("Disk cache okuma hatasi: \(error.localizedDescription)")
            return nil
        }
    }

    /// Ses verisini cache'e kaydeder.
    /// - Parameters:
    ///   - data: Kaydedilecek ses verisi.
    ///   - key: Cache anahtari.
    func set(_ data: Data, for key: String) {
        let cacheKey = cacheKey(for: key)

        // Memory cache
        memoryCache.setObject(data as NSData, forKey: cacheKey as NSString, cost: data.count)

        // Disk cache
        let fileURL = diskFileURL(for: cacheKey)
        do {
            try data.write(to: fileURL)
            logger.debug("Cache kaydedildi: \(key.prefix(30)) (\(data.count) bytes)")
        } catch {
            logger.warning("Disk cache yazma hatasi: \(error.localizedDescription)")
        }
    }

    /// Tum cache'i temizler (memory + disk).
    func clearAll() {
        memoryCache.removeAllObjects()

        do {
            if FileManager.default.fileExists(atPath: diskCacheURL.path) {
                try FileManager.default.removeItem(at: diskCacheURL)
                createDiskCacheDirectoryIfNeeded()
            }
            logger.info("Tum TTS cache temizlendi")
        } catch {
            logger.warning("Disk cache temizleme hatasi: \(error.localizedDescription)")
        }
    }

    // MARK: - Private

    private func cacheKey(for text: String) -> String {
        // Basit hash - metin + voice bilgisi ile
        let data = Data(text.utf8)
        let hash = data.reduce(0) { ($0 &<< 5) &- $0 &+ UInt64($1) }
        return String(hash, radix: 16)
    }

    private func diskFileURL(for key: String) -> URL {
        diskCacheURL.appendingPathComponent("\(key).mp3")
    }

    private func createDiskCacheDirectoryIfNeeded() {
        if !FileManager.default.fileExists(atPath: diskCacheURL.path) {
            do {
                try FileManager.default.createDirectory(at: diskCacheURL, withIntermediateDirectories: true)
            } catch {
                logger.warning("Disk cache dizini olusturulamadi: \(error.localizedDescription)")
            }
        }
    }
}
