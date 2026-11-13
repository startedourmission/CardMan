"""CardMan.app 메뉴바 제목을 파일로 쓴다. rumps를 쓰지 않는다."""

from config import load_config, write_menubar_title


def main():
    write_menubar_title("카드맨")
    from menubar_app import CardManMenuBar

    app = CardManMenuBar()
    stats = app.analyze_messages()
    if not stats:
        write_menubar_title("카드맨")
        return
    percentage = (stats["total"] / app.yearly_budget) * 100
    if percentage > 100:
        write_menubar_title(f"⚠️ {percentage:.0f}%")
    else:
        write_menubar_title(f"₩ {percentage:.0f}%")


if __name__ == "__main__":
    main()
