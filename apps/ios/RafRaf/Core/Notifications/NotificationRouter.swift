import Foundation
import os

/// Deep link hedefleri.
/// Bildirime tiklandiginda yonlendirilecek ekranlar.
enum NotificationDestination: Sendable, Equatable {
    case chat(sessionId: String)
    case approval(approvalId: String)
    case project(projectId: String)
    case settings
    case home
}

/// Bildirim deep link parser.
/// Bildirim payload'indaki deep_link URL'ini hedef ekrana donusturur.
enum NotificationRouter {

    private static let logger = AppLogger.logger(for: "NotificationRouter")

    /// Deep link URL string'ini hedef ekrana donusturur.
    /// - Parameter deepLink: Deep link URL string'i (orn. "rafraf://chat/abc-123").
    /// - Returns: Yonlendirilecek ekran, gecersiz URL icin nil.
    static func destination(from deepLink: String?) -> NotificationDestination? {
        guard let deepLink, let url = URL(string: deepLink) else {
            return nil
        }

        return destination(from: url)
    }

    /// Deep link URL'ini hedef ekrana donusturur.
    /// - Parameter url: Deep link URL'i.
    /// - Returns: Yonlendirilecek ekran, gecersiz URL icin nil.
    static func destination(from url: URL) -> NotificationDestination? {
        guard url.scheme == "rafraf" else {
            logger.warning("Bilinmeyen URL scheme: \(url.scheme ?? "nil")")
            return nil
        }

        let host = url.host()
        let pathComponents = url.pathComponents.filter { $0 != "/" }

        switch host {
        case "chat":
            if let sessionId = pathComponents.first {
                logger.info("Deep link: chat/\(sessionId)")
                return .chat(sessionId: sessionId)
            }
            return .chat(sessionId: "")
        case "approval":
            if let approvalId = pathComponents.first {
                logger.info("Deep link: approval/\(approvalId)")
                return .approval(approvalId: approvalId)
            }
            return nil
        case "project":
            if let projectId = pathComponents.first {
                logger.info("Deep link: project/\(projectId)")
                return .project(projectId: projectId)
            }
            return nil
        case "settings":
            logger.info("Deep link: settings")
            return .settings
        default:
            logger.warning("Bilinmeyen deep link host: \(host ?? "nil")")
            return nil
        }
    }
}
