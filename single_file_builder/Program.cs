using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Threading;
using System.Windows.Forms;

namespace ReferenceCheckerSingleFile
{
    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            try
            {
                string exePath = Assembly.GetExecutingAssembly().Location;
                string versionStamp = ComputeHash(exePath).Substring(0, 12);
                string cacheRoot = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "ReferenceCheckerSingleFile");
                string extractRoot = Path.Combine(cacheRoot, versionStamp);

                Directory.CreateDirectory(cacheRoot);

                using (var mutex = new Mutex(false, @"Global\ReferenceCheckerSingleFile_" + versionStamp))
                {
                    bool lockTaken = mutex.WaitOne(TimeSpan.FromMinutes(2));
                    if (!lockTaken)
                    {
                        throw new InvalidOperationException("Failed to acquire extraction lock.");
                    }

                    try
                    {
                        EnsureExtracted(extractRoot);
                        CleanupOldCaches(cacheRoot, versionStamp);
                    }
                    finally
                    {
                        mutex.ReleaseMutex();
                    }
                }

                LaunchApplication(extractRoot);
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "Single-file launcher failed.\r\n\r\n" + ex,
                    "ReferenceChecker.SingleFile",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }

        private static void EnsureExtracted(string extractRoot)
        {
            string markerPath = Path.Combine(extractRoot, ".extract_ok");
            string appPath = Path.Combine(extractRoot, "ReferenceChecker.exe");

            if (File.Exists(markerPath) && File.Exists(appPath))
            {
                return;
            }

            if (Directory.Exists(extractRoot))
            {
                Directory.Delete(extractRoot, true);
            }

            Directory.CreateDirectory(extractRoot);

            Assembly assembly = Assembly.GetExecutingAssembly();
            string resourceName = assembly.GetManifestResourceNames()
                .FirstOrDefault(name => name.EndsWith("payload.zip", StringComparison.OrdinalIgnoreCase));

            if (string.IsNullOrEmpty(resourceName))
            {
                throw new FileNotFoundException("Embedded payload.zip was not found.");
            }

            using (Stream stream = assembly.GetManifestResourceStream(resourceName))
            {
                if (stream == null)
                {
                    throw new FileNotFoundException("Embedded payload.zip stream could not be opened.");
                }

                using (var archive = new ZipArchive(stream, ZipArchiveMode.Read))
                {
                    foreach (ZipArchiveEntry entry in archive.Entries)
                    {
                        string destinationPath = Path.Combine(extractRoot, entry.FullName);
                        string destinationDirectory = Path.GetDirectoryName(destinationPath);

                        if (!string.IsNullOrEmpty(destinationDirectory))
                        {
                            Directory.CreateDirectory(destinationDirectory);
                        }

                        if (string.IsNullOrEmpty(entry.Name))
                        {
                            continue;
                        }

                        entry.ExtractToFile(destinationPath, true);
                    }
                }
            }

            File.WriteAllText(markerPath, DateTime.Now.ToString("O"));
        }

        private static void CleanupOldCaches(string cacheRoot, string currentVersionStamp)
        {
            foreach (string directory in Directory.GetDirectories(cacheRoot))
            {
                string name = Path.GetFileName(directory);
                if (string.Equals(name, currentVersionStamp, StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                try
                {
                    Directory.Delete(directory, true);
                }
                catch
                {
                    // Best effort cleanup only.
                }
            }
        }

        private static void LaunchApplication(string extractRoot)
        {
            string appPath = Path.Combine(extractRoot, "ReferenceChecker.exe");
            if (!File.Exists(appPath))
            {
                throw new FileNotFoundException("Extracted ReferenceChecker.exe was not found.", appPath);
            }

            var process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = appPath,
                    WorkingDirectory = extractRoot,
                    UseShellExecute = true
                }
            };

            process.Start();
        }

        private static string ComputeHash(string filePath)
        {
            using (var stream = File.OpenRead(filePath))
            using (var sha256 = SHA256.Create())
            {
                byte[] hash = sha256.ComputeHash(stream);
                return BitConverter.ToString(hash).Replace("-", "");
            }
        }
    }
}
