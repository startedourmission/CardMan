#import <Cocoa/Cocoa.h>
#include <copyfile.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

static const char *kPython = "%PYTHON%";
static const char *kAppScript = "%APP_SCRIPT%";
static const char *kMenubarScript = "%MENUBAR_SCRIPT%";

static int copy_messages_db(const char *dest_dir) {
    const char *home = getenv("HOME");
    FILE *log = fopen("/tmp/cardman-copy.log", "w");
    if (!home || !dest_dir) {
        if (log) {
            fprintf(log, "missing home or dest\n");
            fclose(log);
        }
        return 1;
    }
    mkdir(dest_dir, 0700);
    const char *names[] = {"chat.db", "chat.db-wal", "chat.db-shm"};
    for (int i = 0; i < 3; i++) {
        char src[PATH_MAX];
        char dst[PATH_MAX];
        snprintf(src, sizeof(src), "%s/Library/Messages/%s", home, names[i]);
        snprintf(dst, sizeof(dst), "%s/%s", dest_dir, names[i]);
        if (copyfile(src, dst, NULL, COPYFILE_DATA) != 0) {
            if (log) {
                fprintf(log, "copyfile %s -> %s: %s\n", src, dst, strerror(errno));
            }
            if (i == 0) {
                if (log) fclose(log);
                return 1;
            }
        } else if (log) {
            fprintf(log, "copied %s\n", names[i]);
        }
    }
    if (log) {
        fprintf(log, "ok %s\n", dest_dir);
        fclose(log);
    }
    return 0;
}

// 메뉴바 아이콘과 메뉴는 menubar_app.py(rumps)가 만든다.
// 이 앱은 전체 디스크 접근 권한을 가진 부모 프로세스로만 남는다.
@interface AppDelegate : NSObject <NSApplicationDelegate>
@property (nonatomic, strong) NSTask *menubarTask;
@property (nonatomic, strong) NSTask *windowTask;
@property (nonatomic, copy) NSString *dbCopyDir;
@end

@implementation AppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    (void)notification;
    fprintf(stderr, "cardman-launcher-v3 launching\n");

    NSString *home = NSHomeDirectory();
    NSString *copyDir = [NSString stringWithFormat:@"%@/Library/Application Support/CardMan/messages", home];
    [[NSFileManager defaultManager] createDirectoryAtPath:copyDir
                              withIntermediateDirectories:YES
                                               attributes:nil
                                                    error:nil];
    if (copy_messages_db([copyDir fileSystemRepresentation]) == 0) {
        self.dbCopyDir = copyDir;
    }

    [self launchMenubar];
}

- (NSTask *)pythonTask:(const char *)script {
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:[NSString stringWithUTF8String:kPython]];
    task.arguments = @[[NSString stringWithUTF8String:script]];
    NSMutableDictionary *env = [[[NSProcessInfo processInfo] environment] mutableCopy];
    env[@"CARDMAN_BUNDLED"] = @"1";
    if (self.dbCopyDir) {
        env[@"CARDMAN_DB_COPY"] = self.dbCopyDir;
    }
    task.environment = env;
    return task;
}

- (void)launchMenubar {
    if (self.menubarTask && self.menubarTask.isRunning) {
        return;
    }
    self.menubarTask = [self pythonTask:kMenubarScript];
    self.menubarTask.terminationHandler = ^(NSTask *task) {
        (void)task;
        dispatch_async(dispatch_get_main_queue(), ^{
            [NSApp terminate:nil];
        });
    };
    NSError *error = nil;
    if (![self.menubarTask launchAndReturnError:&error]) {
        NSLog(@"menubar launch failed: %@", error);
        [NSApp terminate:nil];
    }
}

- (void)launchWindow {
    if (self.windowTask && self.windowTask.isRunning) {
        return;
    }
    self.windowTask = [self pythonTask:kAppScript];
    NSError *error = nil;
    if (![self.windowTask launchAndReturnError:&error]) {
        NSLog(@"window launch failed: %@", error);
    }
}

- (BOOL)applicationShouldHandleReopen:(NSApplication *)sender hasVisibleWindows:(BOOL)flag {
    (void)sender;
    (void)flag;
    [self launchWindow];
    return YES;
}

- (void)applicationWillTerminate:(NSNotification *)notification {
    (void)notification;
    if (self.menubarTask && self.menubarTask.isRunning) {
        [self.menubarTask terminate];
    }
    if (self.windowTask && self.windowTask.isRunning) {
        [self.windowTask terminate];
    }
}

@end

int main(int argc, const char *argv[]) {
    if (argc >= 3 && strcmp(argv[1], "--copy-db") == 0) {
        return copy_messages_db(argv[2]);
    }
    @autoreleasepool {
        NSApplication *app = [NSApplication sharedApplication];
        AppDelegate *delegate = [AppDelegate new];
        app.delegate = delegate;
        [app setActivationPolicy:NSApplicationActivationPolicyAccessory];
        [app run];
    }
    return 0;
}
