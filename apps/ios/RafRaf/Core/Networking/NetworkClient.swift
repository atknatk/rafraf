import Foundation
import os

/// HTTP istek yontemleri.
enum HTTPMethod: String, Sendable {
    case get = "GET"
    case post = "POST"
    case put = "PUT"
    case patch = "PATCH"
    case delete = "DELETE"
}

/// Ag istegi hatalari.
enum NetworkError: Error, Sendable {
    case invalidURL
    case invalidResponse
    case httpError(statusCode: Int)
    case decodingError(Error)
    case noData
    case unauthorized
    case serverError(String)
}

/// REST API istemcisi.
/// URLSession tabanli async ag katmani.
actor NetworkClient {
    private let session: URLSession
    private let baseURL: URL
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    private let logger = Logger(
        subsystem: "com.rafraf",
        category: "NetworkClient"
    )

    init(
        baseURL: URL = AppEnvironment.current.apiBaseURL,
        session: URLSession = .shared
    ) {
        self.baseURL = baseURL
        self.session = session

        let jsonDecoder = JSONDecoder()
        jsonDecoder.keyDecodingStrategy = .convertFromSnakeCase
        jsonDecoder.dateDecodingStrategy = .iso8601
        self.decoder = jsonDecoder

        let jsonEncoder = JSONEncoder()
        jsonEncoder.keyEncodingStrategy = .convertToSnakeCase
        jsonEncoder.dateEncodingStrategy = .iso8601
        self.encoder = jsonEncoder
    }

    /// GET istegi gonderir ve sonucu decode eder.
    func get<T: Decodable & Sendable>(
        path: String,
        queryItems: [URLQueryItem]? = nil
    ) async throws -> T {
        let request = try buildRequest(
            path: path,
            method: .get,
            queryItems: queryItems
        )
        return try await execute(request)
    }

    /// POST istegi gonderir ve sonucu decode eder.
    func post<T: Decodable & Sendable, B: Encodable & Sendable>(
        path: String,
        body: B
    ) async throws -> T {
        var request = try buildRequest(path: path, method: .post)
        request.httpBody = try encoder.encode(body)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        return try await execute(request)
    }

    // MARK: - Private

    private func buildRequest(
        path: String,
        method: HTTPMethod,
        queryItems: [URLQueryItem]? = nil
    ) throws -> URLRequest {
        var components = URLComponents(
            url: baseURL.appendingPathComponent(path),
            resolvingAgainstBaseURL: true
        )
        components?.queryItems = queryItems

        guard let url = components?.url else {
            throw NetworkError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method.rawValue
        return request
    }

    private func execute<T: Decodable & Sendable>(
        _ request: URLRequest
    ) async throws -> T {
        logger.debug("Request: \(request.httpMethod ?? "?") \(request.url?.absoluteString ?? "?")")

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw NetworkError.invalidResponse
        }

        logger.debug("Response: \(httpResponse.statusCode)")

        switch httpResponse.statusCode {
        case 200...299:
            do {
                return try decoder.decode(T.self, from: data)
            } catch {
                throw NetworkError.decodingError(error)
            }
        case 401:
            throw NetworkError.unauthorized
        default:
            throw NetworkError.httpError(statusCode: httpResponse.statusCode)
        }
    }
}
