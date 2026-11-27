package {
    import flash.display.Sprite;
    import flash.events.Event;
    import flash.text.TextField;
    import flash.text.TextFieldType;
    import flash.text.TextFormat;

    public class Test extends Sprite {
        private var first:TextField = field(10);
        private var second:TextField = field(50);

        public function Test() {
            var panel:Sprite = new Sprite();
            panel.cacheAsBitmap = true;
            panel.addChild(first);
            panel.addChild(second);
            addChild(panel);
            stage.focus = first;
            addEventListener(Event.ENTER_FRAME, focusSecond);
        }

        private function field(y:Number):TextField {
            var result:TextField = new TextField();
            result.type = TextFieldType.INPUT;
            result.defaultTextFormat = new TextFormat("_sans", 14);
            result.text = "selected";
            result.y = y;
            result.width = 100;
            result.height = 22;
            result.setSelection(0, result.length);
            return result;
        }

        private function focusSecond(event:Event):void {
            removeEventListener(Event.ENTER_FRAME, focusSecond);
            stage.focus = second;
            trace(stage.focus == second, first.selectionEndIndex, second.selectionEndIndex);
        }
    }
}
