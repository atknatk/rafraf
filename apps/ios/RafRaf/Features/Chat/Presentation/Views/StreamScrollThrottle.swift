import Foundation

/// Streaming sohbet sirasinda `scrollToBottom` tetiklemelerini throttling eder.
///
/// V1.x performance fix: streaming icerik buyurken `messages.last?.content`
/// degisiklikleri her token icin spring animasyonu tetikliyordu (animasyon
/// thrash + scroll jitter). Bu yardimci 100ms penceresine sigiyan ardisik
/// scroll tetiklemelerini tek bir cagriya indirir; `chat.stream_end` gibi
/// kritik anlarda `forceFire()` ile bypass yapilabilir.
///
/// SwiftUI native — Combine veya 3rd party gerekmez. `@MainActor` izole;
/// view'in `@State` lifecycle'ina baglidir.
@MainActor
final class StreamScrollThrottle {
    /// Iki ardisik fire arasi minimum sure.
    let interval: Duration

    private var lastFire: ContinuousClock.Instant?
    private let clock = ContinuousClock()

    init(interval: Duration = .milliseconds(100)) {
        self.interval = interval
    }

    /// `true` doner ve son fire zamanini guncellerse cagiran scroll tetikler.
    /// Throttle penceresinde bir baska cagri olduysa `false` doner ve scroll atlanir.
    func shouldFire() -> Bool {
        let now = clock.now
        if let last = lastFire {
            let elapsed = last.duration(to: now)
            if elapsed < interval {
                return false
            }
        }
        lastFire = now
        return true
    }

    /// Throttle penceresini bypass eder — `chat.stream_end` gibi kritik
    /// noktalarda gecikmesiz scroll icin. Cagiran scroll'u uygulamali.
    func forceFire() {
        lastFire = clock.now
    }

    /// Throttle durumunu resetler — yeni bir streaming oturumu basladiginda.
    func reset() {
        lastFire = nil
    }
}
