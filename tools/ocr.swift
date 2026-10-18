import Foundation
import Vision
import AppKit

// usage: ocr image.png ...  ->  prints "file<TAB>text" for every image (the lines Vision reads are joined with " / ")
// macOS only (Vision is the system OCR). It reads the English of the original pictures, which is what tools/render_images.py
// needs as calibration labels (see tools/README.md). Put transparent pictures on an opaque background first: dark text on a
// transparent background is read as nothing.
for path in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: path), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { print("\(path)\t<<no image>>"); continue }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = true
    req.recognitionLanguages = ["en-US"]
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    try? handler.perform([req])
    let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    print("\(URL(fileURLWithPath: path).lastPathComponent)\t\(lines.joined(separator: " / "))")
}
