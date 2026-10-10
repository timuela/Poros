package top.hypixice.poros.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val PorosColorScheme = darkColorScheme(
    primary = Color(0xFF4285F4),
    onPrimary = Color.White,
    background = Color(0xFF121212),
    onBackground = Color(0xFFE6E6E6),
    surface = Color(0xFF1E1E1E),
    onSurface = Color(0xFFE6E6E6),
    surfaceVariant = Color(0xFF2A2A2A),
    onSurfaceVariant = Color(0xFFAAAAAA),
    outline = Color(0xFF3A3A3A),
    error = Color(0xFFFF5252)
)

@Composable
fun PorosTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = PorosColorScheme, content = content)
}
