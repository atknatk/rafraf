@preconcurrency import AVFoundation
import Foundation
import os

/// Ses oturumu yonetimi.
/// AVAudioSession yapilandirmasi, mikrofon izni ve ses capture islemleri.
final class RFAudioSessionManager: @unchecked Sendable {
    private let audioEngine: AVAudioEngine
    private let logger = AppLogger.logger(for: "AudioSession")
    private var audioBufferCallback: ((AVAudioPCMBuffer) -> Void)?
    private var audioLevelCallback: ((AudioLevel) -> Void)?

    /// Ses formati: Linear PCM, 16kHz, mono, 16-bit.
    static let sampleRate: Double = 16000.0
    static let channelCount: AVAudioChannelCount = 1
    /// Tap buffer boyutu (4096 frame = ~256ms at 16kHz).
    static let bufferSize: AVAudioFrameCount = 4096

    init() {
        self.audioEngine = AVAudioEngine()
    }

    // MARK: - Mikrofon Izni

    /// Mikrofon erisim izni durumunu kontrol eder.
    var hasPermission: Bool {
        AVAudioApplication.shared.recordPermission == .granted
    }

    /// Mikrofon erisim izni ister.
    /// - Returns: Izin verildi mi.
    func requestPermission() async -> Bool {
        await withCheckedContinuation { continuation in
            AVAudioApplication.requestRecordPermission { granted in
                continuation.resume(returning: granted)
            }
        }
    }

    // MARK: - Ses Capture

    /// Ses capture'i baslatir.
    /// - Parameters:
    ///   - bufferCallback: Her ses buffer'i icin cagirilir.
    ///   - levelCallback: Her ses seviyesi olcumu icin cagirilir.
    func startCapture(
        bufferCallback: @escaping (AVAudioPCMBuffer) -> Void,
        levelCallback: @escaping (AudioLevel) -> Void
    ) throws {
        self.audioBufferCallback = bufferCallback
        self.audioLevelCallback = levelCallback

        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, options: [.defaultToSpeaker, .allowBluetooth])
        try session.setActive(true)
        logger.info("AVAudioSession aktif edildi")

        let inputNode = audioEngine.inputNode
        let inputFormat = inputNode.outputFormat(forBus: 0)

        // 16kHz mono format olustur
        guard let targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: Self.sampleRate,
            channels: Self.channelCount,
            interleaved: true
        ) else {
            logger.error("Hedef ses formati olusturulamadi")
            throw AudioCaptureError.formatCreationFailed
        }

        // Format converter
        guard let converter = AVAudioConverter(from: inputFormat, to: targetFormat) else {
            logger.error("Ses format donusturucusu olusturulamadi")
            throw AudioCaptureError.converterCreationFailed
        }

        inputNode.installTap(
            onBus: 0,
            bufferSize: Self.bufferSize,
            format: inputFormat
        ) { [weak self] buffer, _ in
            guard let self else { return }

            // Ses seviyesi hesapla
            self.calculateAudioLevel(buffer: buffer)

            // Format donusumu (16kHz mono PCM16)
            let frameCapacity = AVAudioFrameCount(
                Double(buffer.frameLength) * Self.sampleRate / inputFormat.sampleRate
            )
            guard let convertedBuffer = AVAudioPCMBuffer(
                pcmFormat: targetFormat,
                frameCapacity: frameCapacity
            ) else { return }

            var error: NSError?
            converter.convert(to: convertedBuffer, error: &error) { _, outStatus in
                outStatus.pointee = .haveData
                return buffer
            }

            if let error {
                self.logger.error("Ses donusum hatasi: \(error.localizedDescription)")
                return
            }

            self.audioBufferCallback?(convertedBuffer)
        }

        audioEngine.prepare()
        try audioEngine.start()
        logger.info("Ses capture baslatildi - sampleRate: \(Self.sampleRate), channels: \(Self.channelCount)")
    }

    /// Ses capture'i durdurur ve kaynaklari serbest birakir.
    func stopCapture() {
        audioEngine.inputNode.removeTap(onBus: 0)
        audioEngine.stop()

        do {
            try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        } catch {
            logger.warning("AVAudioSession deaktif edilemedi: \(error.localizedDescription)")
        }

        audioBufferCallback = nil
        audioLevelCallback = nil
        logger.info("Ses capture durduruldu")
    }

    // MARK: - Private

    private func calculateAudioLevel(buffer: AVAudioPCMBuffer) {
        guard let channelData = buffer.floatChannelData else { return }

        let channelDataValue = channelData.pointee
        let frameLength = Int(buffer.frameLength)
        guard frameLength > 0 else { return }

        var sum: Float = 0
        var peak: Float = 0

        for index in 0..<frameLength {
            let sample = abs(channelDataValue[index])
            sum += sample * sample
            if sample > peak {
                peak = sample
            }
        }

        let rms = sqrt(sum / Float(frameLength))
        let avgDb = 20 * log10(max(rms, 0.000001))
        let peakDb = 20 * log10(max(peak, 0.000001))

        let level = AudioLevel(
            averagePower: avgDb,
            peakPower: peakDb,
            normalizedLevel: AudioLevel.normalize(decibels: avgDb)
        )

        audioLevelCallback?(level)
    }
}

/// Ses capture hatalari.
enum AudioCaptureError: Error, Sendable {
    case formatCreationFailed
    case converterCreationFailed
}
