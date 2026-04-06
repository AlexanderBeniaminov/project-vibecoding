package com.napominator.ui.record

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.napominator.ui.theme.NapominatorTheme
import dagger.hilt.android.AndroidEntryPoint

// TODO: Этап 4 — полная реализация экрана записи голоса
@AndroidEntryPoint
class RecordActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            NapominatorTheme {
                // Временная заглушка — будет заменена в Этапе 4
            }
        }
    }
}
