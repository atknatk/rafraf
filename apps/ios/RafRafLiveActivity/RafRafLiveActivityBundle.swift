//
//  RafRafLiveActivityBundle.swift
//  RafRafLiveActivity
//
//  Created by Atakan on 01/04/2026.
//

import WidgetKit
import SwiftUI

@main
struct RafRafLiveActivityBundle: WidgetBundle {
    var body: some Widget {
        RafRafLiveActivity()
        TaskLiveActivity()
        if #available(iOS 18.0, *) {
            RafRafLiveActivityControl()
        }
    }
}
